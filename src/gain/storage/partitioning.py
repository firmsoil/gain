from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl
import structlog

from gain.model.pr import PullRequest

log = structlog.get_logger(__name__)

CANONICAL_PR_SCHEMA: dict[str, pl.DataType] = {
    "github_node_id": pl.String(),
    "number": pl.Int64(),
    "repository_name_with_owner": pl.String(),
    "repository_id": pl.String(),
    "author_login": pl.String(),
    "author_type": pl.String(),
    "created_at": pl.Datetime(time_unit="us", time_zone="UTC"),
    "closed_at": pl.Datetime(time_unit="us", time_zone="UTC"),
    "merged_at": pl.Datetime(time_unit="us", time_zone="UTC"),
    "state": pl.String(),
    "is_draft": pl.Boolean(),
    "additions": pl.Int64(),
    "deletions": pl.Int64(),
    "changed_files": pl.Int64(),
    "review_decision": pl.String(),
    "collected_at": pl.Datetime(time_unit="us", time_zone="UTC"),
    "ingestion_run_id": pl.String(),
}


CANONICAL_DEPLOYMENT_SCHEMA: dict[str, pl.DataType] = {
    "id": pl.String(),
    "source_system": pl.String(),
    "repository_name_with_owner": pl.String(),
    "environment": pl.String(),
    "status": pl.String(),
    "commit_sha": pl.String(),
    "ref_name": pl.String(),
    "deployed_by": pl.String(),
    "started_at": pl.Datetime(time_unit="us", time_zone="UTC"),
    "completed_at": pl.Datetime(time_unit="us", time_zone="UTC"),
    "duration_seconds": pl.Float64(),
    "collected_at": pl.Datetime(time_unit="us", time_zone="UTC"),
    "ingestion_run_id": pl.String(),
}

CANONICAL_COMMIT_SCHEMA: dict[str, pl.DataType] = {
    "sha": pl.String(),
    "repository_name_with_owner": pl.String(),
    "author_name": pl.String(),
    "author_email": pl.String(),
    "author_login": pl.String(),
    "committed_at": pl.Datetime(time_unit="us", time_zone="UTC"),
    "message": pl.String(),
    "additions": pl.Int64(),
    "deletions": pl.Int64(),
    "files_changed": pl.Int64(),
    "collected_at": pl.Datetime(time_unit="us", time_zone="UTC"),
    "ingestion_run_id": pl.String(),
}

CANONICAL_ISSUE_SCHEMA: dict[str, pl.DataType] = {
    "id": pl.String(),
    "key": pl.String(),
    "source_system": pl.String(),
    "project_key": pl.String(),
    "title": pl.String(),
    "description": pl.String(),
    "issue_type": pl.String(),
    "status": pl.String(),
    "priority": pl.String(),
    "author": pl.String(),
    "assignee": pl.String(),
    "labels": pl.List(pl.String),
    "story_points": pl.Float64(),
    "created_at": pl.Datetime(time_unit="us", time_zone="UTC"),
    "updated_at": pl.Datetime(time_unit="us", time_zone="UTC"),
    "resolved_at": pl.Datetime(time_unit="us", time_zone="UTC"),
    "due_date": pl.Datetime(time_unit="us", time_zone="UTC"),
    "parent_id": pl.String(),
    "linked_pr_keys": pl.List(pl.String),
    "collected_at": pl.Datetime(time_unit="us", time_zone="UTC"),
    "ingestion_run_id": pl.String(),
}


def get_canonical_schema(entity_type: str | None = None) -> dict[str, pl.DataType]:
    """Return default schema for an entity type when fallback LazyFrame is empty."""
    norm = entity_type.lower().rstrip("s") if entity_type is not None else None
    if norm in (None, "pull_request", "pr"):
        return dict(CANONICAL_PR_SCHEMA)
    if norm == "deployment":
        return dict(CANONICAL_DEPLOYMENT_SCHEMA)
    if norm == "commit":
        return dict(CANONICAL_COMMIT_SCHEMA)
    if norm == "issue":
        return dict(CANONICAL_ISSUE_SCHEMA)
    return {}


def compute_partition_path(entity_type: str, dt: datetime, org: str) -> Path:
    """Compute relative Hive partition path."""
    if dt.tzinfo == UTC:
        utc_dt = dt
    elif dt.tzinfo:
        utc_dt = dt.astimezone(UTC)
    else:
        utc_dt = dt.replace(tzinfo=UTC)
    safe_entity = entity_type.lower().strip()
    safe_org = (org.split("/")[0] if "/" in org else org).strip() or "default"
    return (
        Path(f"entity_type={safe_entity}")
        / f"year={utc_dt.year:04d}"
        / f"month={utc_dt.month:02d}"
        / f"org={safe_org}"
    )


def compute_partition_dir(root_dir: Path, entity_type: str, dt: datetime, org: str) -> Path:
    """Compute absolute Hive partition directory under a root path."""
    return root_dir / compute_partition_path(entity_type, dt, org)


class PartitionedWriter:
    """Writes dataset records or Polars DataFrames into Hive-partitioned directory layout."""

    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def write_partition(
        self,
        df: pl.DataFrame,
        entity_type: str,
        year: int,
        month: int,
        org: str,
        filename: str | None = None,
    ) -> Path:
        """Atomically write a single partition DataFrame to Parquet."""
        safe_entity = entity_type.lower().strip()
        safe_org = (org.split("/")[0] if "/" in org else org).strip() or "default"
        part_dir = (
            self.root_dir
            / f"entity_type={safe_entity}"
            / f"year={year:04d}"
            / f"month={month:02d}"
            / f"org={safe_org}"
        )
        part_dir.mkdir(parents=True, exist_ok=True)

        fname = filename or f"part_{uuid.uuid4().hex[:12]}.parquet"
        if not fname.endswith(".parquet"):
            fname = f"{fname}.parquet"

        tmp_path = part_dir / f"{fname}.tmp"
        target_path = part_dir / fname
        df.write_parquet(tmp_path)
        tmp_path.replace(target_path)
        return target_path

    def write_dataframe(
        self,
        df: pl.DataFrame,
        entity_type: str = "pull_request",
        date_col: str = "created_at",
        org_col: str = "repository_name_with_owner",
        filename: str | None = None,
    ) -> list[Path]:
        """Split a DataFrame by (year, month, org) and write out each partition atomically."""
        if df.is_empty():
            return []

        # 1. Resolve date column or fallback
        effective_date_col = date_col
        if effective_date_col not in df.columns:
            fallbacks = ["collected_at", "timestamp", "deployed_at", "committed_at"]
            for fb in fallbacks:
                if fb in df.columns:
                    effective_date_col = fb
                    break

        now = datetime.now(UTC)
        if effective_date_col in df.columns:
            col_type = df.schema[effective_date_col]
            if col_type.is_temporal():
                dt_expr = pl.col(effective_date_col)
            elif col_type == pl.String:
                dt_expr = pl.col(effective_date_col).str.to_datetime(time_zone="UTC", strict=False)
            else:
                dt_expr = pl.col(effective_date_col)

            year_expr = (
                pl.coalesce(dt_expr.dt.year(), pl.lit(now.year)).cast(pl.Int64).alias("__year")
            )
            month_expr = (
                pl.coalesce(dt_expr.dt.month(), pl.lit(now.month)).cast(pl.Int64).alias("__month")
            )
        else:
            year_expr = pl.lit(now.year).cast(pl.Int64).alias("__year")
            month_expr = pl.lit(now.month).cast(pl.Int64).alias("__month")

        # 2. Resolve org column or fallback
        effective_org_col = org_col
        if effective_org_col not in df.columns:
            fallbacks = ["org", "owner", "project_key", "repository_id"]
            for fb in fallbacks:
                if fb in df.columns:
                    effective_org_col = fb
                    break

        if effective_org_col in df.columns:
            raw_org = pl.col(effective_org_col).cast(pl.String)
            org_expr = (
                pl.when(raw_org.is_null() | (raw_org.str.strip_chars() == ""))
                .then(pl.lit("default"))
                .otherwise(raw_org.str.split("/").list.first())
                .alias("__org")
            )
        else:
            org_expr = pl.lit("default").alias("__org")

        augmented = df.with_columns(year_expr, month_expr, org_expr)
        partitions = augmented.partition_by(["__year", "__month", "__org"], as_dict=True)

        written_paths: list[Path] = []
        for (y_val, m_val, o_val), part_df in partitions.items():
            clean_part = part_df.drop(["__year", "__month", "__org"])
            y_int = int(y_val)
            m_int = int(m_val)
            o_str = str(o_val)
            p = self.write_partition(
                df=clean_part,
                entity_type=entity_type,
                year=y_int,
                month=m_int,
                org=o_str,
                filename=filename,
            )
            written_paths.append(p)

        return written_paths

    def write_records(
        self,
        records: list[dict[str, Any]],
        entity_type: str = "pull_request",
        date_field: str = "created_at",
        org_field: str = "repository_name_with_owner",
        filename: str | None = None,
    ) -> list[Path]:
        """Write a list of dictionary records partitioned into Hive directories."""
        if not records:
            return []
        df = pl.DataFrame(records)
        return self.write_dataframe(
            df=df,
            entity_type=entity_type,
            date_col=date_field,
            org_col=org_field,
            filename=filename,
        )

    def write_canonical_prs(
        self,
        prs: list[PullRequest],
        filename: str | None = None,
    ) -> list[Path]:
        """Write canonical PullRequest models into Hive partitions."""
        if not prs:
            return []
        records = [pr.to_record() for pr in prs]
        return self.write_records(
            records=records,
            entity_type="pull_request",
            date_field="created_at",
            org_field="repository_name_with_owner",
            filename=filename,
        )


class PartitionedReader:
    """Reads or scans Hive-partitioned or flat Parquet datasets using Polars."""

    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir

    def scan(self, entity_type: str | None = None) -> pl.LazyFrame:
        """Scan Parquet dataset with Hive partition pushdown or flat fallback."""
        if not self.root_dir.exists():
            return pl.LazyFrame(schema=get_canonical_schema(entity_type))

        if self.root_dir.is_file():
            return pl.scan_parquet(self.root_dir, hive_partitioning=True)

        # 1. Hive partitioning check with entity_type directory
        norm = entity_type.lower().rstrip("s") if entity_type is not None else None
        if norm is not None:
            entity_dir = self.root_dir / f"entity_type={norm}"
            if not entity_dir.exists() and entity_type:
                entity_dir = self.root_dir / f"entity_type={entity_type}"
            if entity_dir.exists():
                hive_files = list(entity_dir.rglob("*.parquet"))
                if hive_files:
                    return pl.scan_parquet(
                        [str(f) for f in hive_files],
                        hive_partitioning=True,
                    )

        # 2. Find matching parquet files (including flat and partitioned subdirectories)
        all_parquet = sorted(self.root_dir.rglob("*.parquet"))
        matching_files: list[Path] = []
        if norm is not None:
            for f in all_parquet:
                fname = f.name.lower()
                fpath = str(f).lower()
                if norm in ("pull_request", "pr"):
                    if (
                        "pull_request" in fname
                        or "pull_requests" in fname
                        or "prs" in fname
                        or fname.startswith("pr_")
                        or fname.startswith("prs_")
                        or fname == "pr.parquet"
                        or "entity_type=pull_request" in fpath
                    ):
                        matching_files.append(f)
                elif norm == "deployment":
                    if "deployment" in fname or "entity_type=deployment" in fpath:
                        matching_files.append(f)
                elif norm == "commit":
                    if "commit" in fname or "entity_type=commit" in fpath:
                        matching_files.append(f)
                elif norm == "issue":
                    if "issue" in fname or "entity_type=issue" in fpath:
                        matching_files.append(f)
                else:
                    if norm in fname or f"entity_type={norm}" in fpath:
                        matching_files.append(f)

            if not matching_files:
                known = {"pull_request", "deployment", "commit", "issue", "ai_telemetry"}
                other_known = {k for k in known if norm not in k}
                matching_files = [
                    f for f in all_parquet if not any(k in f.name.lower() for k in other_known)
                ]
        else:
            matching_files = all_parquet

        if matching_files:
            return pl.scan_parquet([str(f) for f in matching_files], hive_partitioning=True)

        # 3. Directory exists but has no matching parquet files
        return pl.LazyFrame(schema=get_canonical_schema(entity_type))

    def read(self, entity_type: str | None = None) -> pl.DataFrame:
        """Read and collect all records into a Polars DataFrame."""
        return self.scan(entity_type=entity_type).collect()
