from __future__ import annotations

from datetime import UTC, datetime


def parse_utc_datetime(value: str) -> datetime:
    """Parse an ISO 8601 datetime string and normalize to UTC.

    Handles GitHub API format (trailing 'Z') and timezone-aware/naive inputs.
    """
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def parse_nullable_utc_datetime(value: str | None) -> datetime | None:
    """Parse an optional ISO 8601 datetime string."""
    return None if value is None else parse_utc_datetime(value)
