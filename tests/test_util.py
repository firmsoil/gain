from __future__ import annotations

from datetime import UTC, datetime

from gain.util import parse_nullable_utc_datetime, parse_utc_datetime


def test_parse_utc_datetime_with_z_suffix() -> None:
    dt = parse_utc_datetime("2023-01-01T12:00:00Z")
    assert dt == datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)


def test_parse_utc_datetime_with_plus_0000_suffix() -> None:
    dt = parse_utc_datetime("2023-01-01T12:00:00+00:00")
    assert dt == datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)


def test_parse_utc_datetime_with_non_utc_offset() -> None:
    dt = parse_utc_datetime("2023-01-01T12:00:00-05:00")
    # 12:00:00-05:00 is 17:00:00 UTC
    assert dt == datetime(2023, 1, 1, 17, 0, 0, tzinfo=UTC)


def test_parse_utc_datetime_with_naive_string() -> None:
    dt = parse_utc_datetime("2023-01-01T12:00:00")
    assert dt == datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)


def test_parse_nullable_utc_datetime_with_none() -> None:
    assert parse_nullable_utc_datetime(None) is None


def test_parse_nullable_utc_datetime_with_valid_string() -> None:
    dt = parse_nullable_utc_datetime("2023-01-01T12:00:00Z")
    assert dt == datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)
