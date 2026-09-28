"""SQLAlchemy declarative base and session factory."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def create_session_factory(database_url: str) -> sessionmaker[Session]:
    """Build a session factory bound to a fresh engine for the given URL."""
    engine = create_engine(database_url, future=True)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
