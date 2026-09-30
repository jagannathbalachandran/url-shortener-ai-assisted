"""Integration tests for POST /api/v1/links, through the API to the real DB."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session

from shortener.app import create_app
from shortener.config import Settings
from shortener.db import create_session_factory
from shortener.dependencies import get_clock, get_code_generator
from shortener.models import CODE_LENGTH, MAX_ORIGINAL_URL_LENGTH, Link
from shortener.repository import LinkRepository

TEST_BASE_URL = "http://short.test"
VALID_URL = "https://example.com/article"
FIXED_NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)

INVALID_URLS = [
    "javascript:alert(1)",
    "data:text/plain;base64,aGk=",
    "file:///etc/passwd",
    "ftp://example.com/file",
    "http://",
    "",
    "not a url",
    "https://example.com/" + "a" * MAX_ORIGINAL_URL_LENGTH,
]

INVALID_EXPIRIES = [
    "2020-01-01T00:00:00+00:00",  # in the past
    "2026-06-01T00:00:00",  # no time zone
    "not a date",
]


class SequenceCodeGenerator:
    """Test double that yields codes from a fixed sequence, in order."""

    def __init__(self, codes: list[str]) -> None:
        self._codes = iter(codes)

    def generate(self) -> str:
        return next(self._codes)


@pytest.fixture
def app(database_url: str) -> Iterator[FastAPI]:
    """A real app wired to the migrated test database (no dependency overrides)."""
    application = create_app(
        Settings(database_url=database_url, base_url=TEST_BASE_URL)
    )
    yield application
    application.state.session_factory.kw["bind"].dispose()


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


@pytest.fixture
def db_session(database_url: str) -> Iterator[Session]:
    """An independent, durably-committing session for seeding/verifying via a
    connection separate from the app's own per-request session."""
    factory = create_session_factory(database_url)
    db = factory()
    yield db
    db.execute(delete(Link))
    db.commit()
    db.close()
    factory.kw["bind"].dispose()


def _seed_link(db_session: Session, code: str, original_url: str = VALID_URL) -> None:
    LinkRepository(db_session).add(
        Link(code=code, original_url=original_url, created_at=datetime.now(UTC))
    )


def test_create_link_returns_201_with_code_and_short_url(client: TestClient) -> None:
    response = client.post("/api/v1/links", json={"url": VALID_URL})

    assert response.status_code == 201
    body = response.json()
    assert len(body["code"]) == CODE_LENGTH
    assert body["short_url"] == f"{TEST_BASE_URL}/{body['code']}"
    assert body["original_url"] == VALID_URL


def test_link_is_committed_before_response_and_readable_via_repository(
    client: TestClient, db_session: Session
) -> None:
    response = client.post("/api/v1/links", json={"url": VALID_URL})
    code = response.json()["code"]

    # db_session is a separate DB connection from the one the app used to
    # handle the request, so finding the row here proves LinkService already
    # committed it (via LinkRepository.add) before the response was returned.
    found = LinkRepository(db_session).get_by_code(code)

    assert found is not None
    assert found.original_url == VALID_URL


@pytest.mark.parametrize("url", INVALID_URLS)
def test_rejects_invalid_urls_with_422(client: TestClient, url: str) -> None:
    response = client.post("/api/v1/links", json={"url": url})

    assert response.status_code == 422


def test_same_url_submitted_twice_gets_different_codes(client: TestClient) -> None:
    first = client.post("/api/v1/links", json={"url": VALID_URL})
    second = client.post("/api/v1/links", json={"url": VALID_URL})

    assert first.json()["code"] != second.json()["code"]


def test_original_url_is_stored_exactly_as_submitted(client: TestClient) -> None:
    url = "https://example.com/no-trailing-slash"

    response = client.post("/api/v1/links", json={"url": url})

    assert response.json()["original_url"] == url


def test_collision_is_retried_and_succeeds_with_the_next_code(
    app: FastAPI, client: TestClient, db_session: Session
) -> None:
    _seed_link(db_session, "AAAAAAA")
    app.dependency_overrides[get_code_generator] = lambda: SequenceCodeGenerator(
        ["AAAAAAA", "AAAAAAA", "BBBBBBB"]
    )

    response = client.post("/api/v1/links", json={"url": VALID_URL})

    assert response.status_code == 201
    assert response.json()["code"] == "BBBBBBB"


def test_retry_exhaustion_returns_503(
    app: FastAPI, client: TestClient, db_session: Session
) -> None:
    _seed_link(db_session, "CCCCCCC")
    app.dependency_overrides[get_code_generator] = lambda: SequenceCodeGenerator(
        ["CCCCCCC"] * 5
    )

    response = client.post("/api/v1/links", json={"url": VALID_URL})

    assert response.status_code == 503


def test_create_link_without_expiry_returns_null_expires_at(client: TestClient) -> None:
    response = client.post("/api/v1/links", json={"url": VALID_URL})

    assert response.json()["expires_at"] is None


def test_create_link_with_future_expiry_returns_it_normalized_to_utc(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/links",
        json={"url": VALID_URL, "expires_at": "2026-12-31T23:59:59+02:00"},
    )

    assert response.status_code == 201
    assert response.json()["expires_at"] == "2026-12-31T21:59:59Z"


@pytest.mark.parametrize("expires_at", INVALID_EXPIRIES)
def test_create_link_rejects_invalid_expiry_with_422(
    client: TestClient, expires_at: str
) -> None:
    response = client.post(
        "/api/v1/links", json={"url": VALID_URL, "expires_at": expires_at}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_expiry"


def test_create_link_rejects_expiry_equal_to_now_with_422(
    app: FastAPI, client: TestClient
) -> None:
    app.dependency_overrides[get_clock] = lambda: lambda: FIXED_NOW

    response = client.post(
        "/api/v1/links",
        json={"url": VALID_URL, "expires_at": FIXED_NOW.isoformat()},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_expiry"
