"""Integration tests for GET /api/v1/links/{code}/stats."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session

from shortener.app import create_app
from shortener.config import Settings
from shortener.db import create_session_factory
from shortener.models import Click, Link
from shortener.repository import ClickRepository, LinkRepository

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
    db.execute(delete(Click))
    db.execute(delete(Link))
    db.commit()
    db.close()
    factory.kw["bind"].dispose()


def _seed_link(db_session: Session, code: str, original_url: str = VALID_URL) -> Link:
    return LinkRepository(db_session).add(
        Link(code=code, original_url=original_url, created_at=datetime.now(UTC))
    )


def _seed_click(
    db_session: Session, link_id: int, clicked_at: datetime, referrer_host: str
) -> None:
    ClickRepository(db_session).add(
        Click(link_id=link_id, clicked_at=clicked_at, referrer_host=referrer_host)
    )


def test_stats_returns_totals_per_day_and_top_referrers_including_direct(
    client: TestClient, db_session: Session
) -> None:
    link = _seed_link(db_session, "AAAAAAA")
    now = datetime.now(UTC)
    day1 = now - timedelta(days=2)
    day2 = now - timedelta(days=1)
    _seed_click(db_session, link.id, day1, "example.com")
    _seed_click(db_session, link.id, day1, "example.com")
    _seed_click(db_session, link.id, day2, "(direct)")
    _seed_click(db_session, link.id, day2, "other.example.com")

    response = client.get("/api/v1/links/AAAAAAA/stats")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "AAAAAAA"
    assert body["total_clicks"] == 4
    assert body["clicks_per_day"] == [
        {"date": day1.date().isoformat(), "count": 2},
        {"date": day2.date().isoformat(), "count": 2},
    ]
    assert body["top_referrers"] == [
        {"referrer": "example.com", "count": 2},
        {"referrer": "(direct)", "count": 1},
        {"referrer": "other.example.com", "count": 1},
    ]


def test_stats_for_link_with_no_clicks_returns_zeros_and_empty_lists(
    client: TestClient, db_session: Session
) -> None:
    _seed_link(db_session, "BBBBBBB")

    response = client.get("/api/v1/links/BBBBBBB/stats")

    assert response.status_code == 200
    body = response.json()
    assert body["total_clicks"] == 0
    assert body["clicks_per_day"] == []
    assert body["top_referrers"] == []


def test_unknown_code_returns_404(client: TestClient, db_session: Session) -> None:
    response = client.get("/api/v1/links/ZZZZZZZ/stats")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "not_found"
    assert "message" in body["error"]


@pytest.mark.parametrize("code", MALFORMED_CODES)
def test_malformed_code_returns_404_not_422(
    client: TestClient, db_session: Session, code: str
) -> None:
    response = client.get(f"/api/v1/links/{code}/stats")

    assert response.status_code == 404


def test_stats_response_schema_documents_each_fields_window(app: FastAPI) -> None:
    schema = app.openapi()["components"]["schemas"]["LinkStatsResponse"]["properties"]

    assert "all-time" in schema["total_clicks"]["description"].lower()
    assert "30 days" in schema["clicks_per_day"]["description"]
    assert "all-time" in schema["top_referrers"]["description"].lower()
