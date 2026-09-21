"""Domain service for dataset quality evaluation and health metrics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from gain.config import Settings, get_settings
from gain.model.pr import PullRequest
from gain.quality import validate_pull_requests
from gain.storage.analytics import read_canonical


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

        all_prs: list[PullRequest] = []
        for path in sorted(canonical_dir.glob("*.parquet")):
            try:
                prs = read_canonical(path)
                all_prs.extend(prs)
            except Exception:
                continue

        total = len(all_prs)
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

        issues = validate_pull_requests(all_prs)
        error_count = sum(1 for i in issues if i.severity == "ERROR")
        valid_records = max(0, total - error_count)
        validity_score = round(valid_records / total, 4) if total > 0 else 0.0

        latest_collected: datetime | None = None
        for p in all_prs:
            if latest_collected is None or p.collected_at > latest_collected:
                latest_collected = p.collected_at

        sufficiency = (
            "SUFFICIENT" if total >= 30 else ("LOW_COUNT" if total >= 5 else "INSUFFICIENT")
        )

        flags = [
            {
                "code": i.code,
                "severity": i.severity,
                "message": i.message,
                "node_id": i.github_node_id,
            }
            for i in issues[:25]
        ]

        gaps: list[str] = []
        if any(p.merged_at is None for p in all_prs):
            gaps.append("Unmerged PRs present (excluded from cycle time per null policy)")
        if any(p.closed_at is None for p in all_prs):
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
