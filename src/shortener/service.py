"""Business logic for creating and resolving short links, and click stats."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Protocol

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from shortener.codegen import BASE62_ALPHABET, CodeGenerator
from shortener.exceptions import (
    CodeCollisionError,
    LinkCreationExhaustedError,
    LinkNotFoundError,
)
from shortener.models import CODE_LENGTH, Click, Link
from shortener.repository import ClickRepository
from shortener.validation import validate_url

MAX_CODE_GENERATION_ATTEMPTS = 5  # ADR-001 D1
CLICKS_PER_DAY_WINDOW_DAYS = 30
TOP_REFERRERS_LIMIT = 5

_CODE_FORMAT_PATTERN = re.compile(f"^[{BASE62_ALPHABET}]{{{CODE_LENGTH}}}$")

_logger = logging.getLogger(__name__)


class LinkWriter(Protocol):
    """Minimal persistence interface LinkService needs from a repository."""

    def add(self, link: Link) -> Link:
        """Persist `link`; raise CodeCollisionError if its code exists."""
        ...


class LinkReader(Protocol):
    """Minimal lookup interface LinkService needs from a repository."""

    def get_by_code(self, code: str) -> Link | None:
        """Return the link stored under `code`, or None if it doesn't exist."""
        ...


def _is_valid_code_format(code: str) -> bool:
    """True if `code` is a well-formed short code (fixed-length base62)."""
    return _CODE_FORMAT_PATTERN.fullmatch(code) is not None


class LinkService:
    """Validates and persists new links, and resolves codes back to links."""

    def __init__(
        self, repository: LinkWriter, code_generator: CodeGenerator, reader: LinkReader
    ) -> None:
        self._repository = repository
        self._code_generator = code_generator
        self._reader = reader

    def create_link(self, url: str) -> Link:
        """Validate `url`, generate a code, and persist the link."""
        original_url = validate_url(url)
        for _ in range(MAX_CODE_GENERATION_ATTEMPTS):
            link = Link(code=self._code_generator.generate(), original_url=original_url)
            try:
                # LinkRepository.add() commits before returning (T-02).
                return self._repository.add(link)
            except CodeCollisionError:
                continue
        raise LinkCreationExhaustedError(MAX_CODE_GENERATION_ATTEMPTS)

    def resolve(self, code: str) -> Link:
        """Return the link for `code`; raise LinkNotFoundError if unknown or malformed."""
        # Malformed codes never reach the repository (FR-3 / no DB query for junk input).
        if not _is_valid_code_format(code):
            raise LinkNotFoundError(code)
        link = self._reader.get_by_code(code)
        if link is None:
            raise LinkNotFoundError(code)
        return link


def record_click_in_background(
    session_factory: sessionmaker[Session], link_id: int, referrer_host: str
) -> None:
    """Record one click for `link_id`, using a fresh session from `session_factory`.

    Runs as a FastAPI background task, after the redirect response is sent
    (ADR-001 D4). Never reuses the request's session -- it's already closed
    by the time background tasks run, so a new session is opened here. Any
    failure is logged (link_id only, never referrer/IP) and swallowed: a
    click-recording failure must never affect the redirect already sent.
    """
    session: Session | None = None
    try:
        session = session_factory()
        ClickRepository(session).add(
            Click(link_id=link_id, referrer_host=referrer_host)
        )
    except SQLAlchemyError:
        _logger.exception("Failed to record click for link_id=%s", link_id)
    finally:
        if session is not None:
            session.close()


class LinkResolver(Protocol):
    """Minimal interface StatsService needs to turn a code into a Link."""

    def resolve(self, code: str) -> Link:
        """Return the link for `code`; raise LinkNotFoundError if unknown or malformed."""
        ...


class ClickReader(Protocol):
    """Minimal aggregate-query interface StatsService needs from a repository."""

    def total_clicks(self, link_id: int) -> int:
        """Return the all-time total number of clicks for `link_id`."""
        ...

    def clicks_per_day(self, link_id: int, since: datetime) -> list[tuple[date, int]]:
        """Return (UTC day, count) pairs for `link_id` at or after `since`."""
        ...

    def top_referrers(self, link_id: int, limit: int) -> list[tuple[str, int]]:
        """Return the top `limit` (referrer host, count) pairs for `link_id`."""
        ...


@dataclass(frozen=True)
class DailyClickCount:
    """One UTC calendar day's click count."""

    day: date
    count: int


@dataclass(frozen=True)
class ReferrerCount:
    """One referrer host's click count."""

    referrer: str
    count: int


@dataclass(frozen=True)
class LinkStats:
    """Click statistics for one link."""

    total_clicks: int
    clicks_per_day: list[DailyClickCount]
    top_referrers: list[ReferrerCount]


def _clicks_per_day_window_start(now: datetime) -> datetime:
    """UTC midnight of (today - 29 days): 30 whole UTC days, today included.

    Calendar-aligned, not a rolling 30*24h window, so there's no partial
    first day.
    """
    today = now.astimezone(UTC).date()
    start_day = today - timedelta(days=CLICKS_PER_DAY_WINDOW_DAYS - 1)
    return datetime.combine(start_day, time.min, tzinfo=UTC)


class StatsService:
    """Computes per-link click statistics from aggregate repository queries."""

    def __init__(
        self,
        link_resolver: LinkResolver,
        click_reader: ClickReader,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._link_resolver = link_resolver
        self._click_reader = click_reader
        self._clock = clock

    def get_stats(self, code: str) -> LinkStats:
        """Return click stats for `code`; raises LinkNotFoundError like resolve()."""
        link = self._link_resolver.resolve(code)
        since = _clicks_per_day_window_start(self._clock())
        per_day = self._click_reader.clicks_per_day(link.id, since)
        top = self._click_reader.top_referrers(link.id, TOP_REFERRERS_LIMIT)
        return LinkStats(
            total_clicks=self._click_reader.total_clicks(link.id),
            clicks_per_day=[DailyClickCount(day=d, count=c) for d, c in per_day],
            top_referrers=[ReferrerCount(referrer=r, count=c) for r, c in top],
        )
