"""SQLAlchemy declarative base and session factory."""

from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import ConnectionPoolEntry

_POSTGRESQL_DIALECT = "postgresql"
_SQLITE_DIALECT = "sqlite"


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def _force_utc_session_timezone(engine: Engine) -> None:
    """Set every new Postgres connection's session TimeZone to UTC.

    Stored timestamptz values are always UTC instants regardless of this
    setting, but Postgres's date()/EXTRACT() convert to the *session*
    TimeZone before truncating -- without this, per-day click bucketing
    (ClickRepository.clicks_per_day) would follow the server's configured
    zone instead of UTC. SQLite has no session-timezone concept, so this
    is a no-op there.
    """
    if engine.dialect.name != _POSTGRESQL_DIALECT:
        return

    @event.listens_for(engine, "connect")
    def _set_utc(  # pragma: no cover -- postgres-only, exercised in CI
        dbapi_connection: DBAPIConnection, _record: ConnectionPoolEntry
    ) -> None:
        previous_autocommit = dbapi_connection.autocommit
        dbapi_connection.autocommit = True
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("SET TIME ZONE 'UTC'")
        finally:
            cursor.close()
        dbapi_connection.autocommit = previous_autocommit


def _enable_sqlite_foreign_keys(engine: Engine) -> None:
    """Turn on foreign-key enforcement for every new SQLite connection.

    SQLite ignores FK constraints -- including clicks.link_id's ON DELETE
    CASCADE -- unless this pragma is set per-connection. Without it, a
    deleted link's clicks would be silently orphaned instead of cascading,
    unlike Postgres, which always enforces FKs.
    """
    if engine.dialect.name != _SQLITE_DIALECT:
        return  # pragma: no cover -- exercised only in CI's Postgres run

    @event.listens_for(engine, "connect")
    def _set_foreign_keys_on(
        dbapi_connection: DBAPIConnection, _record: ConnectionPoolEntry
    ) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()


def create_session_factory(database_url: str) -> sessionmaker[Session]:
    """Build a session factory bound to a fresh engine for the given URL."""
    engine = create_engine(database_url, future=True)
    _force_utc_session_timezone(engine)
    _enable_sqlite_foreign_keys(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
