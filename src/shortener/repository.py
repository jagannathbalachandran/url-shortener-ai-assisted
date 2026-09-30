"""Repository for persisting and retrieving links and clicks."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shortener.exceptions import CodeCollisionError
from shortener.models import Click, Link

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


class ClickRepository:
    """Persists and aggregates Click records via an injected session.

    All aggregates run as GROUP BY queries in the database -- click rows are
    never loaded into Python for counting (T-06 constraint).
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, click: Click) -> Click:
        """Persist a new click and return it."""
        self._session.add(click)
        self._session.commit()
        self._session.refresh(click)
        return click

    def total_clicks(self, link_id: int) -> int:
        """Return the all-time total number of clicks recorded for `link_id`."""
        stmt = select(func.count()).select_from(Click).where(Click.link_id == link_id)
        return self._session.execute(stmt).scalar_one()

    def clicks_per_day(self, link_id: int, since: datetime) -> list[tuple[date, int]]:
        """Return (UTC day, count) pairs for `link_id` at or after `since`.

        Days with no clicks are omitted; results are sorted ascending by day.
        """
        # Labeled "click_count", not "count": Row is tuple-like and already
        # has a `.count()` method, which would shadow attribute access here.
        day = func.date(Click.clicked_at, type_=Date).label("day")
        stmt = (
            select(day, func.count().label("click_count"))
            .where(Click.link_id == link_id, Click.clicked_at >= since)
            .group_by(day)
            .order_by(day.asc())
        )
        return [(row.day, row.click_count) for row in self._session.execute(stmt).all()]

    def top_referrers(self, link_id: int, limit: int) -> list[tuple[str, int]]:
        """Return the top `limit` (referrer host, count) pairs for `link_id`.

        All-time, ordered by count descending; ties broken alphabetically by
        referrer host for deterministic output.
        """
        stmt = (
            select(Click.referrer_host, func.count().label("click_count"))
            .where(Click.link_id == link_id)
            .group_by(Click.referrer_host)
            .order_by(func.count().desc(), Click.referrer_host.asc())
            .limit(limit)
        )
        return [
            (row.referrer_host, row.click_count)
            for row in self._session.execute(stmt).all()
        ]
