from __future__ import annotations

import uuid
from pathlib import Path

import polars as pl

from gain.metrics.cycle_time import CycleTimeObservation
from gain.metrics.monthly_stats import MonthlyPRStats
from gain.model.pr import PullRequest
from gain.storage.partitioning import CANONICAL_PR_SCHEMA, PartitionedReader


def write_canonical(prs: list[PullRequest], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [pr.to_record() for pr in prs]
    tmp_path = path.with_name(f"{path.stem}_{uuid.uuid4().hex[:8]}.tmp")
    pl.DataFrame(rows).write_parquet(tmp_path)
    tmp_path.replace(path)


def read_canonical(path: Path) -> list[PullRequest]:
    df = pl.read_parquet(path)
    valid_fields = set(PullRequest.model_fields.keys())
    return [
        PullRequest.model_validate({k: v for k, v in row.items() if k in valid_fields})
        for row in df.to_dicts()
    ]


def scan_canonical(canonical_dir: Path, entity_type: str = "pull_request") -> pl.LazyFrame:
    """Scan canonical datasets using Hive partitioning with flat file fallback."""
    return PartitionedReader(canonical_dir).scan(entity_type=entity_type)


def write_cycle_time_observations(observations: list[CycleTimeObservation], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [observation.__dict__ for observation in observations]
    tmp_path = path.with_name(f"{path.stem}_{uuid.uuid4().hex[:8]}.tmp")
    pl.DataFrame(rows).write_parquet(tmp_path)
    tmp_path.replace(path)


def write_monthly_stats(stats: list[MonthlyPRStats], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [s.to_dict() for s in stats]
    tmp_path = path.with_name(f"{path.stem}_{uuid.uuid4().hex[:8]}.tmp")
    pl.DataFrame(rows).write_parquet(tmp_path)
    tmp_path.replace(path)


def read_monthly_stats(path: Path) -> list[MonthlyPRStats]:
    df = pl.read_parquet(path)
    return [MonthlyPRStats(**row) for row in df.to_dicts()]


__all__ = [
    "CANONICAL_PR_SCHEMA",
    "read_canonical",
    "read_monthly_stats",
    "scan_canonical",
    "write_canonical",
    "write_cycle_time_observations",
    "write_monthly_stats",
]
