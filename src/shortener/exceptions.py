"""Domain exceptions for the shortener application."""

from __future__ import annotations


class ShortenerError(Exception):
    """Base class for domain-specific errors raised by the application."""


class CodeCollisionError(ShortenerError):
    """Raised when a generated short code already exists in storage."""

    def __init__(self, code: str) -> None:
        super().__init__(f"Code already exists: {code}")
        self.code = code
