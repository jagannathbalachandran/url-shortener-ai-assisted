"""Repository for persisting and retrieving links."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shortener.exceptions import CodeCollisionError
from shortener.models import Link

_READINESS_PROBE = select(1)


def ping_database(session: Session) -> None:
    """Execute a trivial query to confirm the database connection is alive."""
    session.execute(_READINESS_PROBE)


class LinkRepository:
    """Persists and retrieves Link records via an injected session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, link: Link) -> Link:
        """Persist a new link; raises CodeCollisionError if its code exists."""
        self._session.add(link)
        try:
            self._session.commit()
        except IntegrityError as exc:
            self._session.rollback()
            raise CodeCollisionError(link.code) from exc
        self._session.refresh(link)
        return link

    def get_by_code(self, code: str) -> Link | None:
        """Return the link with the given code, or None if not found."""
        stmt = select(Link).where(Link.code == code)
        return self._session.execute(stmt).scalar_one_or_none()
