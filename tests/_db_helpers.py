"""Shared helpers for building an Alembic config pointed at a specific database."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config

REPO_ROOT = Path(__file__).resolve().parent.parent


def alembic_config(database_url: str) -> Config:
    """Build an Alembic Config for the given database URL."""
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config
