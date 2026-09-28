"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette import status

from shortener.config import Settings, get_settings
from shortener.db import create_session_factory
from shortener.exceptions import InvalidUrlError, LinkCreationExhaustedError
from shortener.routes import router


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build a FastAPI app: wires the DB session factory, routes, error handling."""
    resolved_settings = settings or get_settings()
    app = FastAPI(title="URL Shortener")
    app.state.settings = resolved_settings
    app.state.session_factory = create_session_factory(resolved_settings.database_url)
    app.include_router(router)
    app.add_exception_handler(InvalidUrlError, _handle_invalid_url)
    app.add_exception_handler(LinkCreationExhaustedError, _handle_creation_exhausted)
    return app


def _handle_invalid_url(request: Request, exc: Exception) -> JSONResponse:
    """Map InvalidUrlError to a 422 response."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={"detail": str(exc)}
    )


def _handle_creation_exhausted(request: Request, exc: Exception) -> JSONResponse:
    """Map LinkCreationExhaustedError to a 503 response."""
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content={"detail": str(exc)}
    )
