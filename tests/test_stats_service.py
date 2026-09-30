"""Unit tests for StatsService, using fakes for the link resolver and click reader."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from shortener.exceptions import LinkNotFoundError
from shortener.models import Link
from shortener.service import CLICKS_PER_DAY_WINDOW_DAYS, ReferrerCount, StatsService

VALID_CODE = "AAAAAAA"


class FakeLinkResolver:
    """Resolves to a fixed link, or raises LinkNotFoundError like resolve()."""

    def __init__(self, link: Link | None) -> None:
        self._link = link

    def resolve(self, code: str) -> Link:
        if self._link is None:
            raise LinkNotFoundError(code)
        return self._link


class SpyClickReader:
    """Returns fixed aggregate data; records the `since` it was called with."""

    def __init__(
        self,
        total: int = 0,
        per_day: list[tuple[date, int]] | None = None,
        top_referrers: list[tuple[str, int]] | None = None,
    ) -> None:
        self._total = total
        self._per_day = per_day or []
        self._top_referrers = top_referrers or []
        self.clicks_per_day_since: datetime | None = None

    def total_clicks(self, link_id: int) -> int:
        return self._total

    def clicks_per_day(self, link_id: int, since: datetime) -> list[tuple[date, int]]:
        self.clicks_per_day_since = since
        return self._per_day

    def top_referrers(self, link_id: int, limit: int) -> list[tuple[str, int]]:
        return self._top_referrers[:limit]


def _link() -> Link:
    return Link(id=1, code=VALID_CODE, original_url="https://example.com")


def test_get_stats_raises_not_found_for_an_unknown_or_malformed_code() -> None:
    service = StatsService(FakeLinkResolver(None), SpyClickReader())

    with pytest.raises(LinkNotFoundError):
        service.get_stats("ZZZZZZZ")


def test_get_stats_assembles_totals_per_day_and_top_referrers() -> None:
    reader = SpyClickReader(
        total=5,
        per_day=[(date(2026, 1, 1), 2), (date(2026, 1, 2), 3)],
        top_referrers=[("example.com", 4), ("(direct)", 1)],
    )
    service = StatsService(FakeLinkResolver(_link()), reader)

    stats = service.get_stats(VALID_CODE)

    assert stats.total_clicks == 5
    assert [(d.day, d.count) for d in stats.clicks_per_day] == [
        (date(2026, 1, 1), 2),
        (date(2026, 1, 2), 3),
    ]
    assert stats.top_referrers == [
        ReferrerCount(referrer="example.com", count=4),
        ReferrerCount(referrer="(direct)", count=1),
    ]


def test_clicks_per_day_window_is_utc_midnight_29_days_before_today() -> None:
    reader = SpyClickReader()
    clock_now = datetime(2026, 1, 31, 15, 45, tzinfo=UTC)
    service = StatsService(FakeLinkResolver(_link()), reader, clock=lambda: clock_now)

    service.get_stats(VALID_CODE)

    expected_since = datetime(2026, 1, 2, 0, 0, tzinfo=UTC)
    assert reader.clicks_per_day_since == expected_since
    span = (clock_now.date() - expected_since.date()).days
    assert span == CLICKS_PER_DAY_WINDOW_DAYS - 1


def test_clicks_per_day_window_has_no_partial_first_day_across_a_month_boundary() -> (
    None
):
    """A click exactly at the window start must be included whole -- the
    window starts at UTC midnight, never partway through a day."""
    reader = SpyClickReader()
    clock_now = datetime(2026, 3, 1, 0, 5, tzinfo=UTC)
    service = StatsService(FakeLinkResolver(_link()), reader, clock=lambda: clock_now)

    service.get_stats(VALID_CODE)

    assert reader.clicks_per_day_since == datetime(2026, 1, 31, 0, 0, tzinfo=UTC)
