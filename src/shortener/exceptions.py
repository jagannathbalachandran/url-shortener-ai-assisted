"""Domain exceptions for the shortener application."""

from __future__ import annotations


class ShortenerError(Exception):
    """Base class for domain-specific errors raised by the application."""


class CodeCollisionError(ShortenerError):
    """Raised when a generated short code already exists in storage."""

    def __init__(self, code: str) -> None:
        super().__init__(f"Code already exists: {code}")
        self.code = code


class InvalidUrlError(ShortenerError):
    """Raised when a submitted URL fails validation."""

    def __init__(self, url: str) -> None:
        super().__init__("Invalid URL")
        self.url = url


class LinkCreationExhaustedError(ShortenerError):
    """Raised when every code-generation attempt collides with an existing code."""

    def __init__(self, attempts: int) -> None:
        super().__init__(f"Failed to generate a unique code after {attempts} attempts")
        self.attempts = attempts
