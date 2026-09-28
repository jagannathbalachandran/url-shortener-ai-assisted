"""Unit tests for LinkService, using fakes for the writer and code generator."""

from __future__ import annotations

import pytest

from shortener.exceptions import (
    CodeCollisionError,
    InvalidUrlError,
    LinkCreationExhaustedError,
)
from shortener.models import Link
from shortener.service import MAX_CODE_GENERATION_ATTEMPTS, LinkService

VALID_URL = "https://example.com"


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


def test_create_link_saves_and_returns_the_link() -> None:
    writer = FakeLinkWriter()
    service = LinkService(writer, FakeCodeGenerator(["AAAAAAA"]))

    link = service.create_link(VALID_URL)

    assert link.code == "AAAAAAA"
    assert link.original_url == VALID_URL
    assert writer.calls == 1


def test_create_link_rejects_invalid_url_without_touching_the_writer() -> None:
    writer = FakeLinkWriter()
    service = LinkService(writer, FakeCodeGenerator([]))

    with pytest.raises(InvalidUrlError):
        service.create_link("javascript:alert(1)")

    assert writer.calls == 0


def test_create_link_retries_on_collision_and_succeeds() -> None:
    writer = FakeLinkWriter(collisions=2)
    service = LinkService(writer, FakeCodeGenerator(["AAAAAAA", "AAAAAAA", "BBBBBBB"]))

    link = service.create_link(VALID_URL)

    assert link.code == "BBBBBBB"
    assert writer.calls == 3


def test_create_link_raises_after_max_attempts() -> None:
    writer = FakeLinkWriter(collisions=MAX_CODE_GENERATION_ATTEMPTS)
    codes = ["AAAAAAA"] * MAX_CODE_GENERATION_ATTEMPTS
    service = LinkService(writer, FakeCodeGenerator(codes))

    with pytest.raises(LinkCreationExhaustedError):
        service.create_link(VALID_URL)

    assert writer.calls == MAX_CODE_GENERATION_ATTEMPTS
