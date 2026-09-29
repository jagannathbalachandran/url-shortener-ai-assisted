"""FastAPI dependency providers: per-request DB session and service wiring."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from shortener.codegen import CodeGenerator, SecureCodeGenerator
from shortener.config import Settings
from shortener.repository import LinkRepository
from shortener.service import LinkService


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
    session: Session = Depends(get_session),
    code_generator: CodeGenerator = Depends(get_code_generator),
) -> LinkService:
    """Build a LinkService wired to a per-request repository and code generator."""
    repository = LinkRepository(session)
    return LinkService(repository, code_generator, reader=repository)
