from __future__ import annotations

from pathlib import Path

from gain.schema import normalize_records
from gain.storage.raw import RawStore


def replay_run(raw_dir: Path, ingestion_run_id: str):
    records = RawStore(raw_dir).read_run(ingestion_run_id)
    return normalize_records(records)
