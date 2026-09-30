"""URL and expiry validation for link creation."""

from __future__ import annotations

import unicodedata
from datetime import UTC, datetime
from urllib.parse import urlsplit

from shortener.exceptions import InvalidExpiryError, InvalidUrlError
from shortener.models import MAX_ORIGINAL_URL_LENGTH

ALLOWED_URL_SCHEMES = frozenset({"http", "https"})


def validate_url(url: str) -> str:
    """Return `url` unchanged if it's a well-formed http(s) URL, else raise.

    Only the raw input is checked: nothing is trimmed or normalized, so a URL
    with embedded whitespace/control characters is rejected, not cleaned up.
    """
    if not url or len(url) > MAX_ORIGINAL_URL_LENGTH or _has_disallowed_chars(url):
        raise InvalidUrlError(url)
    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        raise InvalidUrlError(url) from exc
    if parsed.scheme.lower() not in ALLOWED_URL_SCHEMES or not parsed.hostname:
        raise InvalidUrlError(url)
    return url


def _has_disallowed_chars(url: str) -> bool:
    """True if `url` contains whitespace or a control character."""
    return any(ch.isspace() or unicodedata.category(ch) == "Cc" for ch in url)


def validate_expiry(raw_expires_at: str | None, now: datetime) -> datetime | None:
    """Return `raw_expires_at` parsed to a UTC datetime, or None if absent.

    Rejects (as InvalidExpiryError) a value that fails to parse as ISO 8601,
    has no time zone, or is not strictly in the future relative to `now`
    (ADR-002 D1/D3): in the past or equal to now are both invalid.
    """
    if raw_expires_at is None:
        return None
    try:
        parsed = datetime.fromisoformat(raw_expires_at)
    except ValueError as exc:
        raise InvalidExpiryError(raw_expires_at) from exc
    if parsed.tzinfo is None:
        raise InvalidExpiryError(raw_expires_at)
    parsed_utc = parsed.astimezone(UTC)
    if parsed_utc <= now:
        raise InvalidExpiryError(raw_expires_at)
    return parsed_utc
