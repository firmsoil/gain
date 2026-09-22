"""Columnar Parquet persistence for canonical commits."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import structlog

from gain.config import get_settings
from gain.model.commit import CanonicalCommit

log = structlog.get_logger(__name__)


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

    from gain.storage.analytics import scan_canonical

    lf = scan_canonical(target_dir, entity_type="commit")
    if repository:
        lf = lf.filter(pl.col("repository_name_with_owner") == repository)

    try:
        df = lf.collect()
        if len(df) == 0:
            return []
        return [CanonicalCommit.model_validate(row) for row in df.to_dicts()]
    except Exception as exc:
        log.warning("storage_scan_skipped", exc_info=exc)
        return []
