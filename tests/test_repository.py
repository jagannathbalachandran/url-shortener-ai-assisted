"""Tests for LinkRepository."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import StatementError
from sqlalchemy.orm import Session

from shortener.exceptions import CodeCollisionError
from shortener.models import Link
from shortener.repository import LinkRepository

ORIGINAL_URL = "https://example.com"


def _make_link(code: str, original_url: str = ORIGINAL_URL) -> Link:
    return Link(code=code, original_url=original_url, created_at=datetime.now(UTC))


def test_add_and_get_by_code_round_trips(session: Session) -> None:
    repo = LinkRepository(session)
    saved = repo.add(_make_link("AAAAAAA"))

    found = repo.get_by_code("AAAAAAA")

    assert found is not None
    assert found.id == saved.id
    assert found.original_url == ORIGINAL_URL


def test_get_by_code_unknown_returns_none(session: Session) -> None:
    repo = LinkRepository(session)

    assert repo.get_by_code("ZZZZZZZ") is None


def test_add_duplicate_code_raises_collision_error(session: Session) -> None:
    repo = LinkRepository(session)
    repo.add(_make_link("BBBBBBB"))

    with pytest.raises(CodeCollisionError):
        repo.add(_make_link("BBBBBBB", "https://other.example.com"))


def test_session_usable_after_collision_error(session: Session) -> None:
    repo = LinkRepository(session)
    repo.add(_make_link("CCCCCCC"))

    with pytest.raises(CodeCollisionError):
        repo.add(_make_link("CCCCCCC"))

    saved = repo.add(_make_link("DDDDDDD"))

    assert saved.code == "DDDDDDD"
    assert repo.get_by_code("DDDDDDD") is not None


def test_created_at_round_trips_as_timezone_aware_utc(session: Session) -> None:
    repo = LinkRepository(session)
    original = datetime(2026, 1, 1, 12, 30, tzinfo=UTC)
    link = Link(code="EEEEEEE", original_url=ORIGINAL_URL, created_at=original)
    repo.add(link)

    found = repo.get_by_code("EEEEEEE")

    assert found is not None
    assert found.created_at.tzinfo is not None
    assert found.created_at.utcoffset() == timedelta(0)
    assert found.created_at == original


def test_add_rejects_naive_created_at(session: Session) -> None:
    repo = LinkRepository(session)
    naive = Link(
        code="FFFFFFF",
        original_url=ORIGINAL_URL,
        created_at=datetime(2026, 1, 1),  # noqa: DTZ001 -- deliberately naive input
    )

    with pytest.raises(StatementError, match="timezone-aware"):
        repo.add(naive)
