from __future__ import annotations

from pathlib import Path

import polars as pl

from gain.metrics.cycle_time import CycleTimeObservation
from gain.metrics.monthly_stats import MonthlyPRStats
from gain.model.pr import PullRequest


def write_canonical(prs: list[PullRequest], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [pr.to_record() for pr in prs]
    pl.DataFrame(rows).write_parquet(path)


def read_canonical(path: Path) -> list[PullRequest]:
    df = pl.read_parquet(path)
    return [PullRequest.model_validate(row) for row in df.to_dicts()]


def write_cycle_time_observations(observations: list[CycleTimeObservation], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [observation.__dict__ for observation in observations]
    pl.DataFrame(rows).write_parquet(path)


def write_monthly_stats(stats: list[MonthlyPRStats], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [s.to_dict() for s in stats]
    pl.DataFrame(rows).write_parquet(path)


def read_monthly_stats(path: Path) -> list[MonthlyPRStats]:
    df = pl.read_parquet(path)
    return [MonthlyPRStats(**row) for row in df.to_dicts()]
