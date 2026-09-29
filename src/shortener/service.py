"""Business logic for creating and resolving short links."""

from __future__ import annotations

import re
from typing import Protocol

from shortener.codegen import BASE62_ALPHABET, CodeGenerator
from shortener.exceptions import (
    CodeCollisionError,
    LinkCreationExhaustedError,
    LinkNotFoundError,
)
from shortener.models import CODE_LENGTH, Link
from shortener.validation import validate_url

MAX_CODE_GENERATION_ATTEMPTS = 5  # ADR-001 D1

_CODE_FORMAT_PATTERN = re.compile(f"^[{BASE62_ALPHABET}]{{{CODE_LENGTH}}}$")


class LinkWriter(Protocol):
    """Minimal persistence interface LinkService needs from a repository."""

    def add(self, link: Link) -> Link:
        """Persist `link`; raise CodeCollisionError if its code exists."""
        ...


class LinkReader(Protocol):
    """Minimal lookup interface LinkService needs from a repository."""

    def get_by_code(self, code: str) -> Link | None:
        """Return the link stored under `code`, or None if it doesn't exist."""
        ...


def _is_valid_code_format(code: str) -> bool:
    """True if `code` is a well-formed short code (fixed-length base62)."""
    return _CODE_FORMAT_PATTERN.fullmatch(code) is not None


class LinkService:
    """Validates and persists new links, and resolves codes back to links."""

    def __init__(
        self, repository: LinkWriter, code_generator: CodeGenerator, reader: LinkReader
    ) -> None:
        self._repository = repository
        self._code_generator = code_generator
        self._reader = reader

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

    def resolve(self, code: str) -> Link:
        """Return the link for `code`; raise LinkNotFoundError if unknown or malformed."""
        # Malformed codes never reach the repository (FR-3 / no DB query for junk input).
        if not _is_valid_code_format(code):
            raise LinkNotFoundError(code)
        link = self._reader.get_by_code(code)
        if link is None:
            raise LinkNotFoundError(code)
        return link
