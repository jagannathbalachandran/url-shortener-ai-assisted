"""API routes for link creation."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from shortener.config import Settings
from shortener.dependencies import get_current_settings, get_link_service
from shortener.schemas import CreateLinkRequest, LinkResponse
from shortener.service import LinkService

router = APIRouter(prefix="/api/v1/links", tags=["links"])


@router.post("", response_model=LinkResponse, status_code=status.HTTP_201_CREATED)
def create_link(
    body: CreateLinkRequest,
    service: LinkService = Depends(get_link_service),
    settings: Settings = Depends(get_current_settings),
) -> LinkResponse:
    """Create a short link for `body.url` and return its short URL."""
    link = service.create_link(body.url)
    return LinkResponse.from_link(link, settings.base_url)
