"""Parquet persistence for canonical AI developer telemetry."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import structlog

from gain.config import get_settings
from gain.model.ai import AiDeveloperTelemetry

log = structlog.get_logger(__name__)


def write_ai_telemetry(records: list[AiDeveloperTelemetry], path: Path) -> None:
    """Write AI telemetry records to Parquet file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [r.model_dump(mode="python") for r in records]
    pl.DataFrame(rows).write_parquet(path)


def read_ai_telemetry(path: Path) -> list[AiDeveloperTelemetry]:
    """Read AI telemetry records from a Parquet file."""
    if not path.exists():
        return []
    df = pl.read_parquet(path)
    return [AiDeveloperTelemetry.model_validate(row) for row in df.to_dicts()]


def load_ai_telemetry_for_repo(
    repo: str, canonical_dir: Path | None = None
) -> list[AiDeveloperTelemetry]:
    """Search canonical directory for AI telemetry files matching the given repo."""
    target_dir = canonical_dir or get_settings().canonical_dir
    if not target_dir.exists():
        return []

    matching_records: list[AiDeveloperTelemetry] = []
    for file_path in target_dir.glob("*ai_telemetry*.parquet"):
        try:
            records = read_ai_telemetry(file_path)
            matching_records.extend([r for r in records if r.repository == repo])
        except (FileNotFoundError, Exception) as exc:
            log.warning("storage_file_skipped", file_path=str(file_path), exc_info=exc)
            continue

    return matching_records
