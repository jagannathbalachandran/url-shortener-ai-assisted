"""Integration tests for GET /{code}, through the API to the real DB."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from urllib.parse import unquote

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session

from shortener.app import create_app
from shortener.config import Settings
from shortener.db import create_session_factory
from shortener.models import Link
from shortener.repository import LinkRepository

TEST_BASE_URL = "http://short.test"
VALID_URL = "https://example.com/article"

MALFORMED_CODES = ["AAAAAA", "AAAAAAAA", "AAAAA-A"]


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
    return TestClient(app, follow_redirects=False)


@pytest.fixture
def db_session(database_url: str) -> Iterator[Session]:
    """An independent, durably-committing session for seeding via a connection
    separate from the app's own per-request session."""
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


def test_known_code_redirects_with_exact_location_and_no_store(
    client: TestClient, db_session: Session
) -> None:
    url = "https://example.com/path?q=1&x=2#frag"
    _seed_link(db_session, "AAAAAAA", url)

    response = client.get("/AAAAAAA")

    assert response.status_code == 302
    assert response.headers["location"] == url
    assert response.headers["cache-control"] == "no-store"


def test_unknown_code_returns_404(client: TestClient, db_session: Session) -> None:
    response = client.get("/ZZZZZZZ")

    assert response.status_code == 404
    assert "detail" in response.json()


@pytest.mark.parametrize("code", MALFORMED_CODES)
def test_malformed_code_returns_404_not_422(
    client: TestClient, db_session: Session, code: str
) -> None:
    response = client.get(f"/{code}")

    assert response.status_code == 404


def test_case_differing_code_returns_404(
    client: TestClient, db_session: Session
) -> None:
    _seed_link(db_session, "AAAAAAA")

    response = client.get("/aaaaaaa")

    assert response.status_code == 404


def test_docs_and_openapi_still_reachable_after_root_route_is_added(
    client: TestClient,
) -> None:
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_round_trip_create_then_redirect_lands_on_the_submitted_url(
    client: TestClient,
) -> None:
    url = "https://example.com/path?q=1&x=2#frag"
    created = client.post("/api/v1/links", json={"url": url}).json()

    response = client.get(f"/{created['code']}")

    assert response.status_code == 302
    assert response.headers["location"] == url


def test_round_trip_with_latin1_range_accented_path_is_percent_encoded(
    client: TestClient,
) -> None:
    url = "https://example.com/café"

    created = client.post("/api/v1/links", json={"url": url}).json()
    response = client.get(f"/{created['code']}")

    assert response.status_code == 302
    location = response.headers["location"]
    assert location.isascii()
    assert "caf%C3%A9" in location
    assert unquote(location) == url


def test_round_trip_with_non_latin1_path_is_percent_encoded_not_500(
    client: TestClient,
) -> None:
    url = "https://example.com/日本語-\U0001f389"

    created = client.post("/api/v1/links", json={"url": url}).json()
    response = client.get(f"/{created['code']}")

    assert response.status_code == 302
    location = response.headers["location"]
    assert location.isascii()
    assert unquote(location) == url
