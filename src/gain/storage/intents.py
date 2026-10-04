"""Columnar Parquet persistence for canonical development intents (SE 3.0 assets)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl
import structlog

from gain.config import get_settings
from gain.model.intent import CanonicalIntent, IntentTurn

log = structlog.get_logger(__name__)


def write_canonical_intents(intents: list[CanonicalIntent], path: Path) -> None:
    """Write canonical intents to Parquet file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [intent.to_record() for intent in intents]
    pl.DataFrame(rows).write_parquet(path)


def read_canonical_intents(path: Path) -> list[CanonicalIntent]:
    """Read canonical intents from a Parquet file."""
    if not path.exists():
        return []
    df = pl.read_parquet(path)
    output: list[CanonicalIntent] = []
    for row in df.to_dicts():
        raw_row: dict[str, Any] = dict(row)
        dialogue_json = raw_row.pop("dialogue_history_json", None)
        turns: list[IntentTurn] = []
        if dialogue_json:
            try:
                parsed_turns = json.loads(dialogue_json)
                turns = [IntentTurn.model_validate(t) for t in parsed_turns]
            except Exception as e:
                log.warning("dialogue_deserialization_failed", error=str(e))
        raw_row["dialogue_history"] = turns
        output.append(CanonicalIntent.model_validate(raw_row))
    return output


def load_intents_for_repo(
    repository: str | None = None,
    canonical_dir: Path | None = None,
) -> list[CanonicalIntent]:
    """Load canonical intents filtered by repository name."""
    target_dir = canonical_dir or get_settings().canonical_dir
    if not target_dir.exists():
        return []

    matching: list[CanonicalIntent] = []
    for file_path in target_dir.glob("*intent*.parquet"):
        try:
            intents = read_canonical_intents(file_path)
            if repository:
                matching.extend([i for i in intents if i.repository == repository])
            else:
                matching.extend(intents)
        except (FileNotFoundError, Exception) as exc:
            log.warning("storage_file_skipped", file_path=str(file_path), exc_info=exc)
            continue

    return matching
