"""Tests for validate_url."""

from __future__ import annotations

import pytest

from shortener.exceptions import InvalidUrlError
from shortener.models import MAX_ORIGINAL_URL_LENGTH
from shortener.validation import validate_url

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
