"""Unit tests for LinkService, using fakes for the writer and code generator."""

from __future__ import annotations

import pytest

from shortener.exceptions import (
    CodeCollisionError,
    InvalidUrlError,
    LinkCreationExhaustedError,
    LinkNotFoundError,
)
from shortener.models import Link
from shortener.service import MAX_CODE_GENERATION_ATTEMPTS, LinkService

VALID_URL = "https://example.com"
VALID_CODE = "AAAAAAA"


class FakeCodeGenerator:
    """Returns codes from a fixed sequence, in order."""

    def __init__(self, codes: list[str]) -> None:
        self._codes = iter(codes)

    def generate(self) -> str:
        return next(self._codes)


class FakeLinkWriter:
    """Collides on the first `collisions` calls to add(), then succeeds."""

    def __init__(self, collisions: int = 0) -> None:
        self._collisions_left = collisions
        self.calls = 0

    def add(self, link: Link) -> Link:
        self.calls += 1
        if self._collisions_left > 0:
            self._collisions_left -= 1
            raise CodeCollisionError(link.code)
        return link


class FakeLinkReader:
    """A reader unused by create_link tests; always reports the code as unknown."""

    def get_by_code(self, code: str) -> Link | None:
        return None


class SpyLinkReader:
    """Records get_by_code calls and returns a fixed link (or None)."""

    def __init__(self, link: Link | None = None) -> None:
        self._link = link
        self.calls = 0

    def get_by_code(self, code: str) -> Link | None:
        self.calls += 1
        return self._link


def test_create_link_saves_and_returns_the_link() -> None:
    writer = FakeLinkWriter()
    service = LinkService(writer, FakeCodeGenerator(["AAAAAAA"]), FakeLinkReader())

    link = service.create_link(VALID_URL)

    assert link.code == "AAAAAAA"
    assert link.original_url == VALID_URL
    assert writer.calls == 1


def test_create_link_rejects_invalid_url_without_touching_the_writer() -> None:
    writer = FakeLinkWriter()
    service = LinkService(writer, FakeCodeGenerator([]), FakeLinkReader())

    with pytest.raises(InvalidUrlError):
        service.create_link("javascript:alert(1)")

    assert writer.calls == 0


def test_create_link_retries_on_collision_and_succeeds() -> None:
    writer = FakeLinkWriter(collisions=2)
    service = LinkService(
        writer, FakeCodeGenerator(["AAAAAAA", "AAAAAAA", "BBBBBBB"]), FakeLinkReader()
    )

    link = service.create_link(VALID_URL)

    assert link.code == "BBBBBBB"
    assert writer.calls == 3


def test_create_link_raises_after_max_attempts() -> None:
    writer = FakeLinkWriter(collisions=MAX_CODE_GENERATION_ATTEMPTS)
    codes = ["AAAAAAA"] * MAX_CODE_GENERATION_ATTEMPTS
    service = LinkService(writer, FakeCodeGenerator(codes), FakeLinkReader())

    with pytest.raises(LinkCreationExhaustedError):
        service.create_link(VALID_URL)

    assert writer.calls == MAX_CODE_GENERATION_ATTEMPTS


MALFORMED_CODES = ["", "AAAAAA", "AAAAAAAA", "AAAAA-A", "AAAAAA "]


def test_resolve_returns_the_link_for_a_known_code() -> None:
    link = Link(code=VALID_CODE, original_url=VALID_URL)
    reader = SpyLinkReader(link)
    service = LinkService(FakeLinkWriter(), FakeCodeGenerator([]), reader)

    resolved = service.resolve(VALID_CODE)

    assert resolved is link
    assert reader.calls == 1


def test_resolve_raises_not_found_for_an_unknown_well_formed_code() -> None:
    reader = SpyLinkReader(None)
    service = LinkService(FakeLinkWriter(), FakeCodeGenerator([]), reader)

    with pytest.raises(LinkNotFoundError):
        service.resolve("ZZZZZZZ")

    assert reader.calls == 1


@pytest.mark.parametrize("code", MALFORMED_CODES)
def test_resolve_rejects_malformed_codes_without_querying_the_repository(
    code: str,
) -> None:
    reader = SpyLinkReader(None)
    service = LinkService(FakeLinkWriter(), FakeCodeGenerator([]), reader)

    with pytest.raises(LinkNotFoundError):
        service.resolve(code)

    assert reader.calls == 0


def test_resolve_passes_the_code_through_unchanged_for_case_sensitivity() -> None:
    reader = SpyLinkReader(None)
    service = LinkService(FakeLinkWriter(), FakeCodeGenerator([]), reader)

    with pytest.raises(LinkNotFoundError):
        service.resolve("aaaaaaa")

    assert reader.calls == 1
