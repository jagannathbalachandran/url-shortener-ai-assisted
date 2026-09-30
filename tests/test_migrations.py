"""Tests for the Alembic migrations that create the links and clicks tables."""

from __future__ import annotations

import os
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from alembic import command
from tests._db_helpers import alembic_config

LINKS_TABLE = "links"
CLICKS_TABLE = "clicks"


def _migration_database_url(tmp_path: Path) -> str:
    return os.environ.get("DATABASE_URL") or f"sqlite:///{tmp_path / 'migration.db'}"


def _table_names(engine: Engine) -> list[str]:
    with engine.connect() as connection:
        return inspect(connection).get_table_names()


def test_upgrade_head_creates_and_downgrade_removes_links_table(
    tmp_path: Path,
) -> None:
    database_url = _migration_database_url(tmp_path)
    config = alembic_config(database_url)
    engine = create_engine(database_url, future=True)

    try:
        command.upgrade(config, "head")
        assert LINKS_TABLE in _table_names(engine)

        command.downgrade(config, "base")
        assert LINKS_TABLE not in _table_names(engine)
    finally:
        command.upgrade(config, "head")
        engine.dispose()


def test_clicks_migration_preserves_existing_links_through_upgrade_and_downgrade(
    tmp_path: Path,
) -> None:
    database_url = _migration_database_url(tmp_path)
    config = alembic_config(database_url)
    engine = create_engine(database_url, future=True)

    try:
        command.upgrade(config, "0001")
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO links (code, original_url, created_at) "
                    "VALUES (:code, :url, :now)"
                ),
                {
                    "code": "PREEXST",
                    "url": "https://example.com/pre-existing",
                    "now": datetime.now(UTC).isoformat(),
                },
            )

        command.upgrade(config, "head")
        assert CLICKS_TABLE in _table_names(engine)
        with engine.connect() as connection:
            codes: Sequence[str] = (
                connection.execute(text("SELECT code FROM links")).scalars().all()
            )
        assert codes == ["PREEXST"]

        command.downgrade(config, "0001")
        assert CLICKS_TABLE not in _table_names(engine)
        with engine.connect() as connection:
            codes_after_downgrade: Sequence[str] = (
                connection.execute(text("SELECT code FROM links")).scalars().all()
            )
        assert codes_after_downgrade == ["PREEXST"]

        command.downgrade(config, "base")
        assert LINKS_TABLE not in _table_names(engine)
    finally:
        command.upgrade(config, "head")
        engine.dispose()
