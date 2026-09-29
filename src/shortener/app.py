"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI

from shortener.config import Settings, get_settings
from shortener.db import create_session_factory
from shortener.errors import register_exception_handlers
from shortener.health import router as health_router
from shortener.rate_limit import RateLimiter
from shortener.redirects import router as redirects_router
from shortener.routes import router


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build a FastAPI app: wires the DB session factory, routes, error handling."""
    resolved_settings = settings or get_settings()
    app = FastAPI(title="URL Shortener")
    app.state.settings = resolved_settings
    app.state.session_factory = create_session_factory(resolved_settings.database_url)
    app.state.rate_limiter = RateLimiter(
        max_requests=resolved_settings.rate_limit_max_requests,
        window_seconds=resolved_settings.rate_limit_window_seconds,
    )
    register_exception_handlers(app)
    # /health and /ready are single-segment paths and must be registered
    # before the redirect router, or GET /{code} would shadow them (T-05).
    app.include_router(health_router)
    app.include_router(router)
    # Registered last: a root-level catch-all must never shadow /docs, /openapi.json
    # or /api/v1/... routes (T-04).
    app.include_router(redirects_router)
    return app
