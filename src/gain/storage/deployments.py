"""Columnar Parquet persistence for canonical deployment events."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import structlog

from gain.config import get_settings
from gain.model.deployment import CanonicalDeployment, DeploymentEnvironment

log = structlog.get_logger(__name__)


def write_canonical_deployments(deployments: list[CanonicalDeployment], path: Path) -> None:
    """Write canonical deployments to Parquet file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [d.to_record() for d in deployments]
    pl.DataFrame(rows).write_parquet(path)


def read_canonical_deployments(path: Path) -> list[CanonicalDeployment]:
    """Read canonical deployments from a Parquet file."""
    if not path.exists():
        return []
    df = pl.read_parquet(path)
    return [CanonicalDeployment.model_validate(row) for row in df.to_dicts()]


def load_deployments_for_repo(
    repository: str | None = None,
    environment: DeploymentEnvironment | str | None = None,
    canonical_dir: Path | None = None,
) -> list[CanonicalDeployment]:
    """Load canonical deployments optionally filtered by repository and environment."""
    target_dir = canonical_dir or get_settings().canonical_dir
    if not target_dir.exists():
        return []

    from gain.storage.analytics import scan_canonical

    env_str = environment.value if isinstance(environment, DeploymentEnvironment) else environment
    lf = scan_canonical(target_dir, entity_type="deployment")
    if repository:
        lf = lf.filter(pl.col("repository_name_with_owner") == repository)
    if env_str:
        lf = lf.filter(pl.col("environment").str.to_lowercase() == env_str.lower())

    try:
        df = lf.collect()
        if len(df) == 0:
            return []
        return [CanonicalDeployment.model_validate(row) for row in df.to_dicts()]
    except Exception as exc:
        log.warning("storage_scan_skipped", exc_info=exc)
        return []
