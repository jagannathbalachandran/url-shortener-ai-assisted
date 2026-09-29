"""Redirect latency test (T-05.4): p95 of GET /{code} must stay under 50 ms.

Runs against whatever database the `database_url` fixture resolves to --
SQLite locally, Postgres in CI -- via the same fixtures the other
integration tests use, so no CI-specific handling is needed here.
"""

from __future__ import annotations

import math
import time
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
REDIRECT_CODE = "FFFFFFF"
WARMUP_REQUESTS = 20
SAMPLE_REQUESTS = 300
P95_THRESHOLD_MS = 50.0


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


def _percentile(sorted_values: list[float], percentile: float) -> float:
    """Nearest-rank percentile of an already-sorted list of values."""
    rank = max(0, math.ceil(percentile / 100 * len(sorted_values)) - 1)
    return sorted_values[rank]


def test_redirect_p95_latency_is_under_threshold(
    client: TestClient, db_session: Session
) -> None:
    LinkRepository(db_session).add(
        Link(code=REDIRECT_CODE, original_url=VALID_URL, created_at=datetime.now(UTC))
    )

    for _ in range(WARMUP_REQUESTS):
        client.get(f"/{REDIRECT_CODE}")

    durations_ms: list[float] = []
    for _ in range(SAMPLE_REQUESTS):
        start = time.perf_counter()
        client.get(f"/{REDIRECT_CODE}")
        durations_ms.append((time.perf_counter() - start) * 1000)

    durations_ms.sort()
    p50 = _percentile(durations_ms, 50)
    p95 = _percentile(durations_ms, 95)
    p_max = durations_ms[-1]

    assert p95 < P95_THRESHOLD_MS, (
        f"p50={p50:.2f}ms p95={p95:.2f}ms max={p_max:.2f}ms "
        f"(threshold: {P95_THRESHOLD_MS}ms)"
    )
