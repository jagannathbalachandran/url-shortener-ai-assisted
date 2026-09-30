"""Tests for extract_referrer_host."""

from __future__ import annotations

import pytest

from shortener.models import MAX_REFERRER_HOST_LENGTH
from shortener.referrer import DIRECT_REFERRER, extract_referrer_host

MISSING_OR_UNPARSEABLE = [
    None,
    "",
    "not-a-url",
    "http://[::1",
    "http://:8080",
    "https://@",
]


@pytest.mark.parametrize("referer", MISSING_OR_UNPARSEABLE)
def test_falls_back_to_direct(referer: str | None) -> None:
    assert extract_referrer_host(referer) == DIRECT_REFERRER


def test_extracts_lowercase_host_only() -> None:
    assert extract_referrer_host("https://Example.COM/page?q=1#frag") == "example.com"


def test_ignores_port_and_userinfo_when_a_real_host_is_present() -> None:
    assert (
        extract_referrer_host("https://user:pass@example.com:8080/x") == "example.com"
    )


def test_oversized_hostname_falls_back_to_direct() -> None:
    oversized_host = "a" * (MAX_REFERRER_HOST_LENGTH + 1)

    assert extract_referrer_host(f"https://{oversized_host}/path") == DIRECT_REFERRER


def test_hostname_at_max_length_is_accepted() -> None:
    max_length_host = "a" * MAX_REFERRER_HOST_LENGTH

    assert extract_referrer_host(f"https://{max_length_host}/path") == max_length_host
