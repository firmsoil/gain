"""Columnar Parquet persistence for canonical work items / issues."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import structlog

from gain.config import get_settings
from gain.model.issue import CanonicalIssue

log = structlog.get_logger(__name__)


def write_canonical_issues(issues: list[CanonicalIssue], path: Path) -> None:
    """Write canonical issues to Parquet file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [issue.to_record() for issue in issues]
    pl.DataFrame(rows).write_parquet(path)


def read_canonical_issues(path: Path) -> list[CanonicalIssue]:
    """Read canonical issues from a Parquet file."""
    if not path.exists():
        return []
    df = pl.read_parquet(path)
    return [CanonicalIssue.model_validate(row) for row in df.to_dicts()]


def load_issues_for_project_or_repo(
    project_key: str | None = None,
    canonical_dir: Path | None = None,
) -> list[CanonicalIssue]:
    """Load canonical issues filtered by project key."""
    target_dir = canonical_dir or get_settings().canonical_dir
    if not target_dir.exists():
        return []

    matching: list[CanonicalIssue] = []
    for file_path in target_dir.glob("*issue*.parquet"):
        try:
            issues = read_canonical_issues(file_path)
            if project_key:
                matching.extend([i for i in issues if i.project_key == project_key])
            else:
                matching.extend(issues)
        except (FileNotFoundError, Exception) as exc:
            log.warning("storage_file_skipped", file_path=str(file_path), exc_info=exc)
            continue

    return matching
