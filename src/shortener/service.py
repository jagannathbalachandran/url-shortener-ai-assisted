"""Business logic for creating short links."""

from __future__ import annotations

from typing import Protocol

from shortener.codegen import CodeGenerator
from shortener.exceptions import CodeCollisionError, LinkCreationExhaustedError
from shortener.models import Link
from shortener.validation import validate_url

MAX_CODE_GENERATION_ATTEMPTS = 5  # ADR-001 D1


class LinkWriter(Protocol):
    """Minimal persistence interface LinkService needs from a repository."""

    def add(self, link: Link) -> Link:
        """Persist `link`; raise CodeCollisionError if its code exists."""
        ...


class LinkService:
    """Validates, generates a code for, and persists new links."""

    def __init__(self, repository: LinkWriter, code_generator: CodeGenerator) -> None:
        self._repository = repository
        self._code_generator = code_generator

    def create_link(self, url: str) -> Link:
        """Validate `url`, generate a code, and persist the link."""
        original_url = validate_url(url)
        for _ in range(MAX_CODE_GENERATION_ATTEMPTS):
            link = Link(code=self._code_generator.generate(), original_url=original_url)
            try:
                # LinkRepository.add() commits before returning (T-02).
                return self._repository.add(link)
            except CodeCollisionError:
                continue
        raise LinkCreationExhaustedError(MAX_CODE_GENERATION_ATTEMPTS)
