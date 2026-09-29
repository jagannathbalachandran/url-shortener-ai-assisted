"""Integration tests for the rate limiter wired onto POST /api/v1/links."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import delete
from sqlalchemy.orm import Session

from shortener.app import create_app
from shortener.config import Settings
from shortener.db import create_session_factory
from shortener.dependencies import get_rate_limiter
from shortener.models import Link
from shortener.rate_limit import RateLimiter
from shortener.repository import LinkRepository

TEST_BASE_URL = "http://short.test"
VALID_URL = "https://example.com/article"


class FakeClock:
    """A manually-advanced clock for deterministic window tests."""

    def __init__(self, start: float = 0.0) -> None:
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


@pytest.fixture
def app(database_url: str) -> Iterator[FastAPI]:
    """A real app wired to the migrated test database (no dependency overrides)."""
    application = create_app(
        Settings(database_url=database_url, base_url=TEST_BASE_URL)
    )
    yield application
    application.state.session_factory.kw["bind"].dispose()


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


def _post(client: TestClient) -> Response:
    return cast(Response, client.post("/api/v1/links", json={"url": VALID_URL}))


def test_exceeding_limit_returns_429_with_retry_after(app: FastAPI) -> None:
    # A single shared instance: the override is re-resolved on every request,
    # so a fresh RateLimiter per call would never see a prior request's count.
    limiter = RateLimiter(max_requests=2, window_seconds=60.0, clock=FakeClock())
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    client = TestClient(app)

    assert _post(client).status_code == 201
    assert _post(client).status_code == 201
    third = _post(client)

    assert third.status_code == 429
    assert "Retry-After" in third.headers
    assert third.json()["error"]["code"] == "rate_limited"


def test_requests_succeed_again_after_the_window_passes(app: FastAPI) -> None:
    clock = FakeClock()
    limiter = RateLimiter(max_requests=1, window_seconds=60.0, clock=clock)
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    client = TestClient(app)
    assert _post(client).status_code == 201
    assert _post(client).status_code == 429

    clock.advance(60.0)

    assert _post(client).status_code == 201


def test_different_client_ips_have_independent_limits(app: FastAPI) -> None:
    limiter = RateLimiter(max_requests=1, window_seconds=60.0)
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    client_a = TestClient(app, client=("1.2.3.4", 12345))
    client_b = TestClient(app, client=("5.6.7.8", 12345))

    assert _post(client_a).status_code == 201
    assert _post(client_b).status_code == 201
    # A second request from the same IP as client_a is over its own limit.
    assert _post(client_a).status_code == 429


def test_non_create_endpoints_are_not_rate_limited(
    app: FastAPI, db_session: Session
) -> None:
    _seed_link(db_session, "EEEEEEE")
    app.dependency_overrides[get_rate_limiter] = lambda: RateLimiter(
        max_requests=3, window_seconds=60.0
    )
    client = TestClient(app, follow_redirects=False)
    request_count = 10

    for _ in range(request_count):
        assert client.get("/EEEEEEE").status_code == 302
        assert client.get("/api/v1/links/EEEEEEE").status_code == 200
        assert client.get("/health").status_code == 200
        assert client.get("/ready").status_code == 200
