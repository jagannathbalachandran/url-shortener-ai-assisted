"""Integration tests for GET /api/v1/links/{code}, through the API to the real DB."""

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
    return TestClient(app)


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


def _seed_link(
    db_session: Session,
    code: str,
    original_url: str = VALID_URL,
    expires_at: datetime | None = None,
) -> Link:
    return LinkRepository(db_session).add(
        Link(
            code=code,
            original_url=original_url,
            created_at=datetime.now(UTC),
            expires_at=expires_at,
        )
    )


def test_known_code_returns_details_matching_the_create_response(
    client: TestClient,
) -> None:
    created = client.post("/api/v1/links", json={"url": VALID_URL}).json()

    response = client.get(f"/api/v1/links/{created['code']}")

    assert response.status_code == 200
    assert response.json() == created


def test_details_for_an_expired_link_returns_200_with_expires_at(
    client: TestClient, db_session: Session
) -> None:
    past_expiry = datetime(2020, 1, 1, tzinfo=UTC)
    _seed_link(db_session, "EXPIRED", expires_at=past_expiry)

    response = client.get("/api/v1/links/EXPIRED")

    assert response.status_code == 200
    assert response.json()["expires_at"] == "2020-01-01T00:00:00Z"


def test_unknown_code_returns_404(client: TestClient, db_session: Session) -> None:
    response = client.get("/api/v1/links/ZZZZZZZ")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "not_found"
    assert "message" in body["error"]


@pytest.mark.parametrize("code", MALFORMED_CODES)
def test_malformed_code_returns_404_not_422(
    client: TestClient, db_session: Session, code: str
) -> None:
    response = client.get(f"/api/v1/links/{code}")

    assert response.status_code == 404


def test_case_differing_code_returns_404(
    client: TestClient, db_session: Session
) -> None:
    _seed_link(db_session, "AAAAAAA")

    response = client.get("/api/v1/links/aaaaaaa")

    assert response.status_code == 404
