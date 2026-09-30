"""Tests proving click recording on GET /{code}: exactly one click per 302,
none for 404s, deferral to a background task, and failure-safety (T-06 AC2-4)."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import cast

import pytest
from fastapi import BackgroundTasks, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from shortener.app import create_app
from shortener.config import Settings
from shortener.db import create_session_factory
from shortener.dependencies import get_session_factory
from shortener.models import Click, Link
from shortener.redirects import redirect_to_original
from shortener.repository import LinkRepository
from shortener.service import LinkService, record_click_in_background

TEST_BASE_URL = "http://short.test"
VALID_URL = "https://example.com/article"


class _NoCodesGenerator:
    """A CodeGenerator that's never called -- resolve() doesn't generate codes."""

    def generate(self) -> str:
        raise AssertionError("code generation should not happen when resolving")


class _NoWriteRepository:
    """A LinkWriter that's never called -- resolve() doesn't write."""

    def add(self, link: Link) -> Link:
        raise AssertionError("writing should not happen when resolving")


class _FixedLinkReader:
    def __init__(self, link: Link) -> None:
        self._link = link

    def get_by_code(self, code: str) -> Link | None:
        return self._link


def _link_service_for(link: Link) -> LinkService:
    return LinkService(
        _NoWriteRepository(), _NoCodesGenerator(), _FixedLinkReader(link)
    )


def _failing_session_factory() -> sessionmaker[Session]:
    def _raise() -> Session:
        raise SQLAlchemyError("simulated DB failure")

    return cast("sessionmaker[Session]", _raise)


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
    """An independent, durably-committing session for seeding/verifying via a
    connection separate from the app's own per-request session."""
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


def _click_count(db_session: Session, link_id: int) -> int:
    stmt = select(func.count()).select_from(Click).where(Click.link_id == link_id)
    return db_session.execute(stmt).scalar_one()


def test_successful_redirect_records_exactly_one_click(
    client: TestClient, db_session: Session
) -> None:
    link = _seed_link(db_session, "AAAAAAA")

    response = client.get(
        "/AAAAAAA", headers={"Referer": "https://example.com/page?q=1"}
    )

    assert response.status_code == 302
    assert _click_count(db_session, link.id) == 1
    click = db_session.execute(
        select(Click).where(Click.link_id == link.id)
    ).scalar_one()
    assert click.referrer_host == "example.com"


def test_unknown_code_records_no_click(client: TestClient, db_session: Session) -> None:
    response = client.get("/ZZZZZZZ")

    assert response.status_code == 404
    assert db_session.execute(select(func.count()).select_from(Click)).scalar_one() == 0


def test_malformed_code_records_no_click(
    client: TestClient, db_session: Session
) -> None:
    response = client.get("/bad-code")

    assert response.status_code == 404
    assert db_session.execute(select(func.count()).select_from(Click)).scalar_one() == 0


def test_missing_referer_is_recorded_as_direct(
    client: TestClient, db_session: Session
) -> None:
    link = _seed_link(db_session, "BBBBBBB")

    client.get("/BBBBBBB")

    click = db_session.execute(
        select(Click).where(Click.link_id == link.id)
    ).scalar_one()
    assert click.referrer_host == "(direct)"


def test_referer_with_path_and_query_is_stored_as_host_only(
    client: TestClient, db_session: Session
) -> None:
    link = _seed_link(db_session, "CCCCCCC")

    client.get(
        "/CCCCCCC",
        headers={"Referer": "https://ref.example.com/some/path?x=1&y=2#frag"},
    )

    click = db_session.execute(
        select(Click).where(Click.link_id == link.id)
    ).scalar_one()
    assert click.referrer_host == "ref.example.com"


def test_click_write_is_deferred_to_a_background_task() -> None:
    """Calling the route directly (bypassing FastAPI's own attachment of
    BackgroundTasks to the response) proves OUR code only *schedules* the
    write via add_task -- it never performs it inline before returning."""
    link = Link(id=42, code="AAAAAAA", original_url=VALID_URL)
    background_tasks = BackgroundTasks()
    session_factory: sessionmaker[Session] = sessionmaker()

    response = redirect_to_original(
        code="AAAAAAA",
        service=_link_service_for(link),
        background_tasks=background_tasks,
        session_factory=session_factory,
        referrer_host="example.com",
    )

    assert response.status_code == 302
    assert len(background_tasks.tasks) == 1
    task = background_tasks.tasks[0]
    assert task.func is record_click_in_background
    assert task.args == (session_factory, 42, "example.com")


def test_background_task_writes_the_click_when_it_runs(database_url: str) -> None:
    """The other half of the deferral proof: once the scheduled callable
    actually runs (i.e. after the response, per FastAPI/Starlette), it does
    write the click correctly."""
    factory = create_session_factory(database_url)
    try:
        seed_session = factory()
        link = _seed_link(seed_session, "DDDDDDD")
        seed_session.close()

        record_click_in_background(factory, link.id, "example.com")

        verify_session = factory()
        assert _click_count(verify_session, link.id) == 1
        verify_session.execute(delete(Click))
        verify_session.execute(delete(Link))
        verify_session.commit()
        verify_session.close()
    finally:
        factory.kw["bind"].dispose()


def test_click_recording_failure_still_returns_302_and_logs_without_referrer(
    app: FastAPI, db_session: Session, caplog: pytest.LogCaptureFixture
) -> None:
    link = _seed_link(db_session, "EEEEEEE")
    app.dependency_overrides[get_session_factory] = _failing_session_factory
    client = TestClient(app, follow_redirects=False)
    distinctive_referrer = "https://leak-check.example.test/secret/path"

    with caplog.at_level(logging.ERROR):
        response = client.get("/EEEEEEE", headers={"Referer": distinctive_referrer})

    assert response.status_code == 302
    assert response.headers["location"] == VALID_URL
    assert _click_count(db_session, link.id) == 0
    error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert any(str(link.id) in r.getMessage() for r in error_records)
    assert "leak-check.example.test" not in caplog.text
