"""FastAPI dependency providers: per-request DB session and service wiring."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from shortener.codegen import CodeGenerator, SecureCodeGenerator
from shortener.config import Settings
from shortener.exceptions import DatabaseUnavailableError, RateLimitExceededError
from shortener.rate_limit import RateLimiter
from shortener.referrer import extract_referrer_host
from shortener.repository import ClickRepository, LinkRepository, ping_database
from shortener.service import LinkService, StatsService

UNKNOWN_CLIENT_KEY = "unknown"


def get_current_settings(request: Request) -> Settings:
    """Return the Settings this running app instance was built with."""
    settings: Settings = request.app.state.settings
    return settings


def get_session(request: Request) -> Iterator[Session]:
    """Yield a DB session bound to the app's session factory, closed after use."""
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def get_code_generator() -> CodeGenerator:
    """Return the default cryptographically secure code generator."""
    return SecureCodeGenerator()


def get_link_service(
    session: Annotated[Session, Depends(get_session)],
    code_generator: Annotated[CodeGenerator, Depends(get_code_generator)],
) -> LinkService:
    """Build a LinkService wired to a per-request repository and code generator."""
    repository = LinkRepository(session)
    return LinkService(repository, code_generator, reader=repository)


def get_rate_limiter(request: Request) -> RateLimiter:
    """Return the app-wide RateLimiter instance."""
    limiter: RateLimiter = request.app.state.rate_limiter
    return limiter


def enforce_create_rate_limit(
    request: Request, limiter: Annotated[RateLimiter, Depends(get_rate_limiter)]
) -> None:
    """Raise RateLimitExceededError if the requesting client is over its limit."""
    key = request.client.host if request.client else UNKNOWN_CLIENT_KEY
    result = limiter.allow(key)
    if not result.allowed:
        raise RateLimitExceededError(result.retry_after_seconds)


def get_database_health(session: Annotated[Session, Depends(get_session)]) -> None:
    """Raise DatabaseUnavailableError if a trivial query against the DB fails."""
    try:
        ping_database(session)
    except SQLAlchemyError as exc:
        raise DatabaseUnavailableError() from exc


def get_session_factory(request: Request) -> sessionmaker[Session]:
    """Return the app-wide session factory.

    Used by background tasks that need their own session, independent of
    the per-request session (which is closed before background tasks run).
    """
    factory: sessionmaker[Session] = request.app.state.session_factory
    return factory


def get_referrer_host(request: Request) -> str:
    """Return the lowercase referrer host for this request, or "(direct)"."""
    return extract_referrer_host(request.headers.get("referer"))


def get_stats_service(
    link_service: Annotated[LinkService, Depends(get_link_service)],
    session: Annotated[Session, Depends(get_session)],
) -> StatsService:
    """Build a StatsService wired to a per-request click repository."""
    return StatsService(link_service, ClickRepository(session))
