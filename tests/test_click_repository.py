"""Tests for ClickRepository's aggregate queries."""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from shortener.models import Click, Link
from shortener.repository import ClickRepository, LinkRepository

ORIGINAL_URL = "https://example.com"


def _seed_link(session: Session, code: str) -> Link:
    return LinkRepository(session).add(Link(code=code, original_url=ORIGINAL_URL))


def _add_click(
    session: Session, link_id: int, clicked_at: datetime, referrer_host: str
) -> None:
    ClickRepository(session).add(
        Click(link_id=link_id, clicked_at=clicked_at, referrer_host=referrer_host)
    )


def test_click_table_has_no_ip_user_agent_or_full_referrer_url_column() -> None:
    column_names = {column.name for column in Click.__table__.columns}

    assert column_names == {"id", "link_id", "clicked_at", "referrer_host"}


def test_total_clicks_counts_only_this_links_clicks(session: Session) -> None:
    link = _seed_link(session, "AAAAAAA")
    other = _seed_link(session, "BBBBBBB")
    _add_click(session, link.id, datetime(2026, 1, 1, tzinfo=UTC), "example.com")
    _add_click(session, link.id, datetime(2026, 1, 2, tzinfo=UTC), "example.com")
    _add_click(session, other.id, datetime(2026, 1, 1, tzinfo=UTC), "example.com")

    assert ClickRepository(session).total_clicks(link.id) == 2


def test_total_clicks_is_zero_for_a_link_with_no_clicks(session: Session) -> None:
    link = _seed_link(session, "CCCCCCC")

    assert ClickRepository(session).total_clicks(link.id) == 0


def test_clicks_per_day_buckets_by_utc_calendar_day_not_server_timezone(
    session: Session,
) -> None:
    """Regression test: on Postgres, date() of a timestamptz uses the
    session TimeZone unless forced to UTC (see db.py's connect handler). A
    click at 23:30 UTC and one an hour later, at 00:30 UTC the next day,
    must land in two different UTC day buckets -- not be merged into one by
    a non-UTC server/session timezone (CI runs this against Postgres)."""
    link = _seed_link(session, "DDDDDDD")
    _add_click(
        session, link.id, datetime(2026, 1, 1, 23, 30, tzinfo=UTC), "example.com"
    )
    _add_click(session, link.id, datetime(2026, 1, 2, 0, 30, tzinfo=UTC), "example.com")

    per_day = ClickRepository(session).clicks_per_day(
        link.id, since=datetime(2025, 12, 1, tzinfo=UTC)
    )

    assert per_day == [(date(2026, 1, 1), 1), (date(2026, 1, 2), 1)]


def test_clicks_per_day_excludes_clicks_before_since(session: Session) -> None:
    link = _seed_link(session, "EEEEEEE")
    _add_click(session, link.id, datetime(2026, 1, 1, tzinfo=UTC), "example.com")
    _add_click(session, link.id, datetime(2026, 1, 5, tzinfo=UTC), "example.com")

    per_day = ClickRepository(session).clicks_per_day(
        link.id, since=datetime(2026, 1, 3, tzinfo=UTC)
    )

    assert per_day == [(date(2026, 1, 5), 1)]


def test_clicks_per_day_omits_zero_click_days_and_sorts_ascending(
    session: Session,
) -> None:
    link = _seed_link(session, "FFFFFFF")
    _add_click(session, link.id, datetime(2026, 1, 3, tzinfo=UTC), "example.com")
    _add_click(session, link.id, datetime(2026, 1, 1, tzinfo=UTC), "example.com")

    per_day = ClickRepository(session).clicks_per_day(
        link.id, since=datetime(2025, 12, 1, tzinfo=UTC)
    )

    assert per_day == [(date(2026, 1, 1), 1), (date(2026, 1, 3), 1)]


def test_top_referrers_orders_by_count_descending_and_limits(session: Session) -> None:
    link = _seed_link(session, "GGGGGGG")
    for _ in range(4):
        _add_click(session, link.id, datetime(2026, 1, 1, tzinfo=UTC), "a.example.com")
    for _ in range(3):
        _add_click(session, link.id, datetime(2026, 1, 1, tzinfo=UTC), "b.example.com")
    for _ in range(2):
        _add_click(session, link.id, datetime(2026, 1, 1, tzinfo=UTC), "c.example.com")
    _add_click(session, link.id, datetime(2026, 1, 1, tzinfo=UTC), "(direct)")

    top = ClickRepository(session).top_referrers(link.id, limit=3)

    assert top == [("a.example.com", 4), ("b.example.com", 3), ("c.example.com", 2)]


def test_top_referrers_includes_direct_as_a_referrer_value(session: Session) -> None:
    link = _seed_link(session, "HHHHHHH")
    _add_click(session, link.id, datetime(2026, 1, 1, tzinfo=UTC), "example.com")
    _add_click(session, link.id, datetime(2026, 1, 1, tzinfo=UTC), "(direct)")
    _add_click(session, link.id, datetime(2026, 1, 1, tzinfo=UTC), "(direct)")

    top = ClickRepository(session).top_referrers(link.id, limit=5)

    assert top == [("(direct)", 2), ("example.com", 1)]
