"""Pydantic request/response models for the links API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from shortener.models import Link


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
