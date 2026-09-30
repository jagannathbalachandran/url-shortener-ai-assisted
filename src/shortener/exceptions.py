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


class InvalidExpiryError(ShortenerError):
    """Raised when a submitted expires_at fails validation.

    Covers every failure mode alike (malformed, missing time zone, in the
    past, or equal to now) so a client can't distinguish which one occurred.
    """

    def __init__(self, expires_at: str) -> None:
        super().__init__("Invalid expires_at")
        self.expires_at = expires_at


class LinkExpiredError(ShortenerError):
    """Raised when a redirect is requested for a link past its expires_at."""

    def __init__(self, code: str) -> None:
        super().__init__(f"Link has expired: {code}")
        self.code = code


class LinkCreationExhaustedError(ShortenerError):
    """Raised when every code-generation attempt collides with an existing code."""

    def __init__(self, attempts: int) -> None:
        super().__init__(f"Failed to generate a unique code after {attempts} attempts")
        self.attempts = attempts


class LinkNotFoundError(ShortenerError):
    """Raised when a code doesn't resolve to a link, whether malformed or unknown.

    Both cases share one exception and message so a client can't distinguish
    "unknown code" from "malformed code" (no information leak about which
    codes exist or what shape they have).
    """

    def __init__(self, code: str) -> None:
        super().__init__(f"No link found for code: {code}")
        self.code = code


class DatabaseUnavailableError(ShortenerError):
    """Raised when a readiness check finds the database unreachable."""

    def __init__(self) -> None:
        super().__init__("Database is unavailable")


class RateLimitExceededError(ShortenerError):
    """Raised when a client exceeds the request rate limit for an endpoint."""

    def __init__(self, retry_after_seconds: float) -> None:
        super().__init__("Rate limit exceeded")
        self.retry_after_seconds = retry_after_seconds
