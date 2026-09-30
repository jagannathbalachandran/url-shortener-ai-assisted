"""ORM models for the shortener application."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from shortener.db import Base

CODE_LENGTH = 7
MAX_ORIGINAL_URL_LENGTH = 2048
MAX_REFERRER_HOST_LENGTH = 253  # DNS practical maximum hostname length


class UTCDateTime(TypeDecorator[datetime]):
    """Datetime type that always round-trips as timezone-aware UTC.

    SQLite drops timezone info on read for DATETIME columns; this type
    normalizes values on bind and result so behaviour is identical on
    SQLite and Postgres.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        return value.astimezone(UTC)

    def process_result_value(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class Link(Base):
    """A shortened link: a unique code mapped to an original URL."""

    __tablename__ = "links"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(CODE_LENGTH), unique=True, index=True)
    original_url: Mapped[str] = mapped_column(String(MAX_ORIGINAL_URL_LENGTH))
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=lambda: datetime.now(UTC)
    )


class Click(Base):
    """A single recorded redirect click against a link (FR-5)."""

    __tablename__ = "clicks"

    id: Mapped[int] = mapped_column(primary_key=True)
    link_id: Mapped[int] = mapped_column(
        ForeignKey("links.id", ondelete="CASCADE"), index=True
    )
    clicked_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=lambda: datetime.now(UTC)
    )
    referrer_host: Mapped[str] = mapped_column(String(MAX_REFERRER_HOST_LENGTH))
