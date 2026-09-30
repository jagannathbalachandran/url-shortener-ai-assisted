"""Tests for validate_url and validate_expiry."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from shortener.exceptions import InvalidExpiryError, InvalidUrlError
from shortener.models import MAX_ORIGINAL_URL_LENGTH
from shortener.validation import validate_expiry, validate_url

VALID_URLS = [
    "http://example.com",
    "https://example.com/path?q=1#frag",
    "HTTPS://example.com",
    "HtTpS://example.com/mixed-case-scheme",
]

INVALID_SCHEME_URLS = [
    "javascript:alert(1)",
    "data:text/plain;base64,aGk=",
    "file:///etc/passwd",
    "ftp://example.com/file",
]

MALFORMED_URLS = [
    "",
    "not a url",
    "http://",
    "http://[::1",
]

DISALLOWED_CHAR_URLS = [
    " http://example.com",
    "http://example.com ",
    "http://exa mple.com",
    "http://example.com/\tpath",
    "http://example.com/\npath",
    "http://example.com/\x00path",
]

# netloc is non-empty for all of these (a port and/or userinfo only), but
# urlsplit's `hostname` is None -- there is no real host (T-03 AC3: "missing
# host" must be rejected with 422; docs/plan.md T-03: "well-formed URL with a
# real host").
HOSTLESS_URLS = [
    "https://user@/path",
    "http://:8080",
    "https://@",
    "http://user:pass@",
]

# Netloc shapes that look unusual but do carry a real, parseable host and
# must still be accepted.
VALID_URLS_WITH_UNUSUAL_NETLOC = [
    "https://example.com:8080",
    "http://[::1]/",
    "https://user@example.com",
]


@pytest.mark.parametrize("url", VALID_URLS)
def test_accepts_valid_http_and_https_urls(url: str) -> None:
    assert validate_url(url) == url


@pytest.mark.parametrize("url", INVALID_SCHEME_URLS)
def test_rejects_disallowed_schemes(url: str) -> None:
    with pytest.raises(InvalidUrlError):
        validate_url(url)


@pytest.mark.parametrize("url", MALFORMED_URLS)
def test_rejects_malformed_or_hostless_urls(url: str) -> None:
    with pytest.raises(InvalidUrlError):
        validate_url(url)


@pytest.mark.parametrize("url", DISALLOWED_CHAR_URLS)
def test_rejects_whitespace_and_control_characters_without_trimming(url: str) -> None:
    with pytest.raises(InvalidUrlError):
        validate_url(url)


def test_accepts_url_at_max_length() -> None:
    padding = "a" * (MAX_ORIGINAL_URL_LENGTH - len("https://example.com/"))
    url = f"https://example.com/{padding}"

    assert len(url) == MAX_ORIGINAL_URL_LENGTH
    assert validate_url(url) == url


def test_rejects_url_over_max_length() -> None:
    padding = "a" * (MAX_ORIGINAL_URL_LENGTH - len("https://example.com/") + 1)
    url = f"https://example.com/{padding}"

    with pytest.raises(InvalidUrlError):
        validate_url(url)


def test_does_not_rewrite_the_submitted_url() -> None:
    url = "https://example.com/path?q=1"

    assert validate_url(url) == url


@pytest.mark.parametrize("url", HOSTLESS_URLS)
def test_rejects_urls_with_netloc_but_no_real_host(url: str) -> None:
    with pytest.raises(InvalidUrlError):
        validate_url(url)


@pytest.mark.parametrize("url", VALID_URLS_WITH_UNUSUAL_NETLOC)
def test_accepts_urls_with_a_real_host_despite_unusual_netloc(url: str) -> None:
    assert validate_url(url) == url


NOW = datetime(2026, 1, 1, tzinfo=UTC)

NO_TIMEZONE_EXPIRIES = [
    "2026-06-01T00:00:00",
    "2099-01-01T00:00:00.123456",
]

MALFORMED_EXPIRIES = [
    "",
    "not a date",
    "2026-13-01T00:00:00+00:00",
]


def test_validate_expiry_returns_none_for_none() -> None:
    assert validate_expiry(None, NOW) is None


def test_validate_expiry_normalizes_a_future_tz_aware_datetime_to_utc() -> None:
    future = "2026-06-01T12:00:00+02:00"

    result = validate_expiry(future, NOW)

    assert result == datetime(2026, 6, 1, 10, 0, 0, tzinfo=UTC)
    assert result is not None
    assert result.tzinfo == UTC


def test_validate_expiry_rejects_a_past_datetime() -> None:
    past = (NOW - timedelta(seconds=1)).isoformat()

    with pytest.raises(InvalidExpiryError):
        validate_expiry(past, NOW)


def test_validate_expiry_rejects_a_datetime_equal_to_now() -> None:
    with pytest.raises(InvalidExpiryError):
        validate_expiry(NOW.isoformat(), NOW)


@pytest.mark.parametrize("raw", NO_TIMEZONE_EXPIRIES)
def test_validate_expiry_rejects_missing_time_zone(raw: str) -> None:
    with pytest.raises(InvalidExpiryError):
        validate_expiry(raw, NOW)


@pytest.mark.parametrize("raw", MALFORMED_EXPIRIES)
def test_validate_expiry_rejects_malformed_input(raw: str) -> None:
    with pytest.raises(InvalidExpiryError):
        validate_expiry(raw, NOW)
