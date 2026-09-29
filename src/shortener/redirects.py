"""Root-level redirect route: GET /{code} -> 302 to the original URL."""

from __future__ import annotations

import string
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Path, Response

from shortener.dependencies import get_link_service
from shortener.service import LinkService

REDIRECT_STATUS_CODE = 302  # ADR-001 D3
NO_STORE_CACHE_CONTROL = "no-store"

# Every printable, non-space ASCII character. Headers can only carry latin-1
# bytes, so a stored URL with characters outside that range would otherwise
# crash Response's header encoding; percent-encoding just those characters
# keeps ASCII URLs (the overwhelming case, including AC1's exact bytes)
# untouched while still producing a valid, non-crashing Location header.
_LOCATION_SAFE_CHARS = "".join(c for c in string.printable if not c.isspace())

router = APIRouter(tags=["redirects"])


@router.get("/{code}")
def redirect_to_original(
    code: Annotated[str, Path()],
    service: Annotated[LinkService, Depends(get_link_service)],
) -> Response:
    """Redirect to the original URL stored under `code`."""
    link = service.resolve(code)
    location = quote(link.original_url, safe=_LOCATION_SAFE_CHARS, encoding="utf-8")
    return Response(
        status_code=REDIRECT_STATUS_CODE,
        headers={"Location": location, "Cache-Control": NO_STORE_CACHE_CONTROL},
    )
