"""Integration tests for the standard error shape (T-05.2), one per case not
already covered by an existing test (see test_redirects.py / test_health.py /
test_api_rate_limit.py for the unknown-code, readiness and rate-limit cases)."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session

from shortener.app import create_app
from shortener.config import Settings
from shortener.db import create_session_factory
from shortener.dependencies import get_code_generator, get_link_service
from shortener.models import Link
from shortener.repository import LinkRepository

TEST_BASE_URL = "http://short.test"
VALID_URL = "https://example.com/article"


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


def _assert_standard_error_shape(body: dict[str, Any], code: str) -> None:
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["message"], str)
    assert body["error"]["message"]


def test_unknown_route_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    _assert_standard_error_shape(response.json(), "not_found")


def test_method_not_allowed_returns_405_and_keeps_allow_header(
    client: TestClient,
) -> None:
    response = client.delete("/api/v1/links")

    assert response.status_code == 405
    _assert_standard_error_shape(response.json(), "method_not_allowed")
    assert "POST" in response.headers["allow"]


def test_validation_error_has_details_and_does_not_echo_input(
    client: TestClient,
) -> None:
    response = client.post("/api/v1/links", json={"url": 12345})

    assert response.status_code == 422
    body = response.json()
    _assert_standard_error_shape(body, "validation_error")
    assert body["error"]["details"]
    detail = body["error"]["details"][0]
    assert detail["loc"]
    assert "msg" in detail
    assert "12345" not in response.text


def test_invalid_url_returns_422_with_standard_shape(client: TestClient) -> None:
    response = client.post("/api/v1/links", json={"url": "javascript:alert(1)"})

    assert response.status_code == 422
    _assert_standard_error_shape(response.json(), "invalid_url")


def test_code_space_exhaustion_returns_503_with_standard_shape(
    app: FastAPI, client: TestClient, db_session: Session
) -> None:
    _seed_link(db_session, "DDDDDDD")
    app.dependency_overrides[get_code_generator] = lambda: SequenceCodeGenerator(
        ["DDDDDDD"] * 5
    )

    response = client.post("/api/v1/links", json={"url": VALID_URL})

    assert response.status_code == 503
    _assert_standard_error_shape(response.json(), "code_space_exhausted")


def _broken_link_service() -> None:
    raise RuntimeError("boom: something internal went wrong")


def test_unhandled_exception_returns_500_generic_body_and_logs_traceback(
    app: FastAPI, caplog: pytest.LogCaptureFixture
) -> None:
    app.dependency_overrides[get_link_service] = _broken_link_service
    # Unhandled exceptions are re-raised by Starlette after our handler runs
    # (so tests can opt in to seeing them); disable that to inspect the
    # response our handler actually sent.
    no_raise_client = TestClient(app, raise_server_exceptions=False)

    with caplog.at_level(logging.ERROR):
        response = no_raise_client.post("/api/v1/links", json={"url": VALID_URL})

    assert response.status_code == 500
    body = response.json()
    _assert_standard_error_shape(body, "internal_error")
    assert "boom" not in response.text
    assert "Traceback" not in response.text

    error_records = [r for r in caplog.records if r.exc_info]
    logged_excs = [r.exc_info[0] for r in error_records if r.exc_info]
    assert RuntimeError in logged_excs

    log_message = error_records[0].getMessage()
    assert "POST" in log_message
    assert "/api/v1/links" in log_message
    assert "testclient" not in log_message  # TestClient's default client host
    assert VALID_URL not in log_message  # the request body must not be logged
