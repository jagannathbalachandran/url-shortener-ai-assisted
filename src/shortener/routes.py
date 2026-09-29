"""API routes for link creation and lookup."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from shortener.config import Settings
from shortener.dependencies import (
    enforce_create_rate_limit,
    get_current_settings,
    get_link_service,
)
from shortener.schemas import CreateLinkRequest, LinkResponse
from shortener.service import LinkService

router = APIRouter(prefix="/api/v1/links", tags=["links"])


@router.post(
    "",
    response_model=LinkResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(enforce_create_rate_limit)],
)
def create_link(
    body: CreateLinkRequest,
    service: LinkService = Depends(get_link_service),
    settings: Settings = Depends(get_current_settings),
) -> LinkResponse:
    """Create a short link for `body.url` and return its short URL."""
    link = service.create_link(body.url)
    return LinkResponse.from_link(link, settings.base_url)


@router.get("/{code}", response_model=LinkResponse)
def get_link_details(
    code: Annotated[str, Path()],
    service: Annotated[LinkService, Depends(get_link_service)],
    settings: Annotated[Settings, Depends(get_current_settings)],
) -> LinkResponse:
    """Return details for the link stored under `code`."""
    link = service.resolve(code)
    return LinkResponse.from_link(link, settings.base_url)
