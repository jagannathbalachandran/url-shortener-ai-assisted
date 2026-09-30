"""Root-level redirect route: GET /{code} -> 302 to the original URL."""

from __future__ import annotations

import string
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, Path, Response
from sqlalchemy.orm import Session, sessionmaker

from shortener.dependencies import (
    get_link_service,
    get_referrer_host,
    get_session_factory,
)
from shortener.service import LinkService, record_click_in_background

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
    background_tasks: BackgroundTasks,
    session_factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
    referrer_host: Annotated[str, Depends(get_referrer_host)],
) -> Response:
    """Redirect to the original URL stored under `code`.

    Records the click in the background, after the response is sent
    (ADR-001 D4) -- never on the hot path of the redirect itself.
    """
    link = service.resolve_for_redirect(code)
    location = quote(link.original_url, safe=_LOCATION_SAFE_CHARS, encoding="utf-8")
    background_tasks.add_task(
        record_click_in_background, session_factory, link.id, referrer_host
    )
    return Response(
        status_code=REDIRECT_STATUS_CODE,
        headers={"Location": location, "Cache-Control": NO_STORE_CACHE_CONTROL},
    )
