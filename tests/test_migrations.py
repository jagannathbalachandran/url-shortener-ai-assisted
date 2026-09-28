"""Tests for the Alembic migration that creates the links table."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Engine

from alembic import command
from tests._db_helpers import alembic_config

LINKS_TABLE = "links"


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
