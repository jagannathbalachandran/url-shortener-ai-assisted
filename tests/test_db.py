"""Tests for the session factory."""

from __future__ import annotations

from sqlalchemy import text

from shortener.db import create_session_factory


def test_create_session_factory_executes_queries(database_url: str) -> None:
    factory = create_session_factory(database_url)

    with factory() as session:
        result: int = session.execute(text("SELECT 1")).scalar_one()
    factory.kw["bind"].dispose()

    assert result == 1
