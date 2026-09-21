"""Columnar Parquet persistence for canonical commits."""

from __future__ import annotations

from pathlib import Path

import polars as pl

from gain.config import get_settings
from gain.model.commit import CanonicalCommit


def write_canonical_commits(commits: list[CanonicalCommit], path: Path) -> None:
    """Write canonical commits to Parquet file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [c.to_record() for c in commits]
    pl.DataFrame(rows).write_parquet(path)


def read_canonical_commits(path: Path) -> list[CanonicalCommit]:
    """Read canonical commits from a Parquet file."""
    if not path.exists():
        return []
    df = pl.read_parquet(path)
    return [CanonicalCommit.model_validate(row) for row in df.to_dicts()]


def load_commits_for_repo(
    repository: str | None = None,
    canonical_dir: Path | None = None,
) -> list[CanonicalCommit]:
    """Load canonical commits optionally filtered by repository."""
    target_dir = canonical_dir or get_settings().canonical_dir
    if not target_dir.exists():
        return []

    matching: list[CanonicalCommit] = []
    for file_path in target_dir.glob("*commit*.parquet"):
        try:
            records = read_canonical_commits(file_path)
            if repository:
                matching.extend([c for c in records if c.repository_name_with_owner == repository])
            else:
                matching.extend(records)
        except Exception:
            continue

    return matching
