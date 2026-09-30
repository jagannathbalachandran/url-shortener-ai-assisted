"""Pydantic request/response models for the links API."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from shortener.models import Link
from shortener.service import LinkStats


class CreateLinkRequest(BaseModel):
    """Request body for POST /api/v1/links."""

    url: str


class LinkResponse(BaseModel):
    """Response body describing a created short link."""

    code: str
    short_url: str
    original_url: str
    created_at: datetime

    @classmethod
    def from_link(cls, link: Link, base_url: str) -> LinkResponse:
        """Build a response from a persisted `link` and the service's `base_url`."""
        return cls(
            code=link.code,
            short_url=f"{base_url}/{link.code}",
            original_url=link.original_url,
            created_at=link.created_at,
        )


class ClicksPerDayEntry(BaseModel):
    """One UTC calendar day's click count."""

    date: date
    count: int


class ReferrerCountEntry(BaseModel):
    """One referrer host's click count."""

    referrer: str
    count: int


class LinkStatsResponse(BaseModel):
    """Response body for GET /api/v1/links/{code}/stats."""

    code: str = Field(..., description="The link's short code.")
    total_clicks: int = Field(
        ..., description="All-time total number of clicks recorded for this link."
    )
    clicks_per_day: list[ClicksPerDayEntry] = Field(
        ...,
        description=(
            "Click counts per UTC calendar day for the last 30 days (today "
            "and the preceding 29 days), ascending by date. Days with zero "
            "clicks are omitted."
        ),
    )
    top_referrers: list[ReferrerCountEntry] = Field(
        ...,
        description="All-time top 5 referrer hosts by click count, descending.",
    )

    @classmethod
    def from_stats(cls, code: str, stats: LinkStats) -> LinkStatsResponse:
        """Build a response from a domain LinkStats result."""
        return cls(
            code=code,
            total_clicks=stats.total_clicks,
            clicks_per_day=[
                ClicksPerDayEntry(date=d.day, count=d.count)
                for d in stats.clicks_per_day
            ],
            top_referrers=[
                ReferrerCountEntry(referrer=r.referrer, count=r.count)
                for r in stats.top_referrers
            ],
        )
