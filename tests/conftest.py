"""Shared test fixtures: a migrated database engine and isolated sessions."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import ConnectionPoolEntry

from alembic import command
from tests._db_helpers import alembic_config


def _database_url(tmp_path_factory: pytest.TempPathFactory) -> str:
    env_url = os.environ.get("DATABASE_URL")
    if env_url:
        return env_url
    db_path = tmp_path_factory.mktemp("db") / "shortener.db"
    return f"sqlite:///{db_path}"


def _allow_sqlite_savepoints(engine: Engine) -> None:
    """Disable pysqlite's implicit transactions so SAVEPOINTs work correctly."""
    if engine.dialect.name != "sqlite":
        return

    @event.listens_for(engine, "connect")
    def _do_connect(
        dbapi_connection: DBAPIConnection, _record: ConnectionPoolEntry
    ) -> None:
        dbapi_connection.isolation_level = None

    @event.listens_for(engine, "begin")
    def _do_begin(conn: Connection) -> None:
        conn.exec_driver_sql("BEGIN")


@pytest.fixture(scope="session")
def database_url(tmp_path_factory: pytest.TempPathFactory) -> str:
    """A database URL migrated to head for the whole test session."""
    url = _database_url(tmp_path_factory)
    command.upgrade(alembic_config(url), "head")
    return url


@pytest.fixture(scope="session")
def db_engine(database_url: str) -> Iterator[Engine]:
    """An engine bound to the migrated test database."""
    engine = create_engine(database_url, future=True)
    _allow_sqlite_savepoints(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session(db_engine: Engine) -> Iterator[Session]:
    """A session whose changes are rolled back after the test."""
    connection = db_engine.connect()
    outer_transaction = connection.begin()
    factory = sessionmaker(
        bind=connection,
        autoflush=False,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    db_session = factory()
    yield db_session
    db_session.close()
    outer_transaction.rollback()
    connection.close()
