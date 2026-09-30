"""Referrer-host extraction for click recording.

Privacy: only the lowercase host is ever kept -- never the scheme, port,
userinfo, path, query string or fragment of the Referer header.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from shortener.models import MAX_REFERRER_HOST_LENGTH

DIRECT_REFERRER = "(direct)"


def extract_referrer_host(referer: str | None) -> str:
    """Return the lowercase host of `referer`, or DIRECT_REFERRER.

    Falls back to DIRECT_REFERRER when the header is missing/empty, has no
    parseable host, is malformed, or the host is longer than a real DNS
    hostname can be (an oversized value is treated the same as no referrer,
    rather than failing the click recording).
    """
    if not referer:
        return DIRECT_REFERRER
    try:
        hostname = urlsplit(referer).hostname
    except ValueError:
        return DIRECT_REFERRER
    if not hostname or len(hostname) > MAX_REFERRER_HOST_LENGTH:
        return DIRECT_REFERRER
    return hostname.lower()
