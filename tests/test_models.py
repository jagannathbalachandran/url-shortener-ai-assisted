"""Unit tests for the UTCDateTime type decorator's bind/result branches."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy.engine.default import DefaultDialect

from shortener.models import UTCDateTime

DIALECT = DefaultDialect()


def test_process_bind_param_passes_through_none() -> None:
    assert UTCDateTime().process_bind_param(None, DIALECT) is None


def test_process_bind_param_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        UTCDateTime().process_bind_param(datetime(2024, 1, 1), DIALECT)  # noqa: DTZ001


def test_process_result_value_passes_through_none() -> None:
    assert UTCDateTime().process_result_value(None, DIALECT) is None


def test_process_result_value_assumes_utc_for_naive_datetime() -> None:
    naive = datetime(2024, 1, 1, 12, 0, 0)  # noqa: DTZ001
    result = UTCDateTime().process_result_value(naive, DIALECT)

    assert result == datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)


def test_process_result_value_normalizes_aware_datetime_to_utc() -> None:
    plus_two = timezone(timedelta(hours=2))
    aware = datetime(2024, 1, 1, 14, 0, 0, tzinfo=plus_two)

    result = UTCDateTime().process_result_value(aware, DIALECT)

    assert result == datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
