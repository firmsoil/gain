"""Domain service for dataset quality evaluation and health metrics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import polars as pl
import structlog

from gain.config import Settings, get_settings
from gain.storage.analytics import scan_canonical

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class QualityEvaluation:
    dataset_id: str
    total_records: int
    valid_records: int
    freshness_utc: str | None
    completeness_score: float
    validity_score: float
    source_status: str
    population_sufficiency: str  # SUFFICIENT, LOW_COUNT, INSUFFICIENT
    known_gaps: list[str]
    quality_flags: list[dict[str, Any]]


class QualityService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def get_dataset_quality(self, dataset_id: str = "pull_requests") -> QualityEvaluation:
        canonical_dir = self.settings.canonical_dir
        if not canonical_dir.exists():
            return QualityEvaluation(
                dataset_id=dataset_id,
                total_records=0,
                valid_records=0,
                freshness_utc=None,
                completeness_score=0.0,
                validity_score=0.0,
                source_status="NO_DATA",
                population_sufficiency="INSUFFICIENT",
                known_gaps=["No canonical datasets found on disk"],
                quality_flags=[],
            )

        lf = scan_canonical(canonical_dir, entity_type="pull_request")

        # Compute validation conditions in Polars
        annotated_lf = lf.with_columns(
            (pl.int_range(pl.len()).over("github_node_id") > 0).alias("is_dup"),
            (
                pl.col("closed_at").is_not_null() & (pl.col("closed_at") < pl.col("created_at"))
            ).alias("invalid_closed"),
            (
                pl.col("merged_at").is_not_null() & (pl.col("merged_at") < pl.col("created_at"))
            ).alias("invalid_merged"),
            (pl.col("merged_at").is_not_null() & pl.col("closed_at").is_null()).alias(
                "merged_no_closed"
            ),
        )

        agg_df = annotated_lf.select(
            [
                pl.len().alias("total"),
                pl.col("collected_at").max().alias("latest_collected"),
                pl.col("is_dup").sum().alias("dup_count"),
                pl.col("invalid_closed").sum().alias("invalid_closed_count"),
                pl.col("invalid_merged").sum().alias("invalid_merged_count"),
                pl.col("merged_no_closed").sum().alias("merged_no_closed_count"),
                pl.col("merged_at").is_null().any().alias("has_unmerged"),
                pl.col("closed_at").is_null().any().alias("has_open"),
            ]
        ).collect()

        total = int(agg_df["total"][0]) if len(agg_df) > 0 else 0
        if total == 0:
            return QualityEvaluation(
                dataset_id=dataset_id,
                total_records=0,
                valid_records=0,
                freshness_utc=None,
                completeness_score=0.0,
                validity_score=0.0,
                source_status="EMPTY_DATASET",
                population_sufficiency="INSUFFICIENT",
                known_gaps=["Canonical Parquet files exist but contain zero valid records"],
                quality_flags=[],
            )

        latest_collected = agg_df["latest_collected"][0]
        dup_count = int(agg_df["dup_count"][0] or 0)
        invalid_closed_count = int(agg_df["invalid_closed_count"][0] or 0)
        invalid_merged_count = int(agg_df["invalid_merged_count"][0] or 0)
        merged_no_closed_count = int(agg_df["merged_no_closed_count"][0] or 0)
        has_unmerged = bool(agg_df["has_unmerged"][0])
        has_open = bool(agg_df["has_open"][0])

        error_count = dup_count + invalid_closed_count + invalid_merged_count
        valid_records = max(0, total - error_count)
        validity_score = round(valid_records / total, 4) if total > 0 else 0.0

        sufficiency = (
            "SUFFICIENT" if total >= 30 else ("LOW_COUNT" if total >= 5 else "INSUFFICIENT")
        )

        flags: list[dict[str, Any]] = []
        if error_count > 0 or merged_no_closed_count > 0:
            flag_rows = (
                annotated_lf.filter(
                    pl.col("is_dup")
                    | pl.col("invalid_closed")
                    | pl.col("invalid_merged")
                    | pl.col("merged_no_closed")
                )
                .select(
                    [
                        "github_node_id",
                        "is_dup",
                        "invalid_closed",
                        "invalid_merged",
                        "merged_no_closed",
                    ]
                )
                .limit(25)
                .collect()
            )
            for row in flag_rows.to_dicts():
                node_id = str(row["github_node_id"])
                if row["is_dup"]:
                    flags.append(
                        {
                            "code": "DUPLICATE_NODE_ID",
                            "severity": "ERROR",
                            "message": "Duplicate GitHub node ID",
                            "node_id": node_id,
                        }
                    )
                if row["invalid_closed"]:
                    flags.append(
                        {
                            "code": "INVALID_CLOSED_AT",
                            "severity": "ERROR",
                            "message": "closed_at precedes created_at",
                            "node_id": node_id,
                        }
                    )
                if row["invalid_merged"]:
                    flags.append(
                        {
                            "code": "INVALID_MERGED_AT",
                            "severity": "ERROR",
                            "message": "merged_at precedes created_at",
                            "node_id": node_id,
                        }
                    )
                if row["merged_no_closed"]:
                    flags.append(
                        {
                            "code": "MERGED_WITHOUT_CLOSED_AT",
                            "severity": "WARNING",
                            "message": "Merged PR has no closed_at",
                            "node_id": node_id,
                        }
                    )
                if len(flags) >= 25:
                    flags = flags[:25]
                    break

        gaps: list[str] = []
        if has_unmerged:
            gaps.append("Unmerged PRs present (excluded from cycle time per null policy)")
        if has_open:
            gaps.append("Open PR inventory present (WIP observation only)")

        return QualityEvaluation(
            dataset_id=dataset_id,
            total_records=total,
            valid_records=valid_records,
            freshness_utc=latest_collected.isoformat() if latest_collected else None,
            completeness_score=round(valid_records / total, 4),
            validity_score=validity_score,
            source_status="HEALTHY" if error_count == 0 else "WARNING",
            population_sufficiency=sufficiency,
            known_gaps=gaps,
            quality_flags=flags,
        )
