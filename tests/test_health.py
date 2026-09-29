"""Integration tests for GET /health and GET /ready."""

from __future__ import annotations

from collections.abc import Iterator
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from shortener.app import create_app
from shortener.config import Settings
from shortener.dependencies import get_database_health, get_session
from shortener.exceptions import DatabaseUnavailableError

TEST_BASE_URL = "http://short.test"


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


def _failing_get_session() -> Iterator[Session]:
    raise RuntimeError("GET /health must not access the database")
    yield  # pragma: no cover -- makes this a generator function


def _failing_get_database_health() -> None:
    raise DatabaseUnavailableError()


class _BrokenSession:
    """A session stand-in whose `execute` always fails like a dead connection."""

    def execute(self, *args: object, **kwargs: object) -> None:
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))


def _broken_db_get_session() -> Iterator[Session]:
    yield cast(Session, _BrokenSession())


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_makes_no_db_call(app: FastAPI, client: TestClient) -> None:
    app.dependency_overrides[get_session] = _failing_get_session

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_returns_ready_when_db_is_reachable(client: TestClient) -> None:
    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_ready_returns_503_standard_shape_when_db_unavailable(
    app: FastAPI, client: TestClient
) -> None:
    app.dependency_overrides[get_database_health] = _failing_get_database_health

    response = client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "not_ready"
    assert "message" in body["error"]
    assert "DatabaseUnavailableError" not in response.text


def test_ready_returns_503_when_the_trivial_query_actually_fails(
    app: FastAPI, client: TestClient
) -> None:
    """Exercises the real ping_database -> get_database_health failure path,
    not just the DatabaseUnavailableError -> 503 mapping covered above."""
    app.dependency_overrides[get_session] = _broken_db_get_session

    response = client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "not_ready"
    assert "OperationalError" not in response.text
