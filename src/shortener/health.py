"""Liveness and readiness probes: GET /health, GET /ready."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from shortener.dependencies import get_database_health

router = APIRouter(tags=["health"])

_HEALTH_OK_BODY = {"status": "ok"}
_READY_OK_BODY = {"status": "ready"}


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness probe: the process is up. Makes no DB call."""
    return _HEALTH_OK_BODY


@router.get("/ready")
def ready(_: Annotated[None, Depends(get_database_health)]) -> dict[str, str]:
    """Readiness probe: 200 if the database answers a trivial query."""
    return _READY_OK_BODY
