"""URL validation for link creation."""

from __future__ import annotations

import unicodedata
from urllib.parse import urlsplit

from shortener.exceptions import InvalidUrlError
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
