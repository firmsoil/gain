"""Domain service for deterministic engineering metrics and Metric Catalog lookups."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from gain.config import Settings, get_settings
from gain.metrics.catalog import MetricCatalog
from gain.metrics.cycle_time import CycleTimeMetric
from gain.metrics.monthly_stats import MonthlyPRStats, MonthlyStatsMetric
from gain.model.pr import PullRequest
from gain.storage.analytics import read_canonical


@dataclass(frozen=True)
class MetricSummaryResult:
    metric_id: str
    metric_version: int
    metric_name: str
    repository: str | None
    total_evaluated: int
    merged_count: int
    summary_stats: dict[str, float | int | None]
    observations_sample: list[dict[str, Any]]
    data_freshness_utc: str | None


@dataclass(frozen=True)
class CohortComparisonResult:
    metric_id: str
    metric_version: int
    cohort_a_name: str
    cohort_b_name: str
    cohort_a_count: int
    cohort_b_count: int
    cohort_a_stats: dict[str, float | int | None]
    cohort_b_stats: dict[str, float | int | None]
    delta_p50_seconds: float | None
    delta_mean_seconds: float | None
    methodology: str


class MetricService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._catalog: MetricCatalog | None = None

    def get_catalog(self) -> MetricCatalog:
        if self._catalog is None:
            catalog_path = Path("docs/metrics/metric-catalog.yaml")
            if not catalog_path.exists():
                # Fallback check relative to workspace
                catalog_path = (
                    self.settings.output_dir.parent / "docs" / "metrics" / "metric-catalog.yaml"
                )
            self._catalog = MetricCatalog(catalog_path)
        return self._catalog

    def get_metric_definition(self, metric_id: str, version: int | None = None) -> dict[str, Any]:
        catalog = self.get_catalog()
        metric_def = catalog.get(metric_id)
        if version is not None and metric_def.get("metric_version") != version:
            raise KeyError(f"Metric {metric_id} version {version} not found in catalog")
        return metric_def

    def _load_canonical_prs(self, repository: str | None = None) -> list[PullRequest]:
        canonical_dir = self.settings.canonical_dir
        if not canonical_dir.exists():
            return []

        all_prs: list[PullRequest] = []
        for file_path in sorted(canonical_dir.glob("*.parquet")):
            try:
                prs = read_canonical(file_path)
                all_prs.extend(prs)
            except Exception:
                continue

        if repository:
            return [p for p in all_prs if p.repository_name_with_owner == repository]
        return all_prs

    def query_pr_cycle_time(
        self,
        repository: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> MetricSummaryResult:
        prs = self._load_canonical_prs(repository=repository)
        if start_date:
            prs = [p for p in prs if p.created_at >= start_date]
        if end_date:
            prs = [p for p in prs if p.created_at <= end_date]

        observations = CycleTimeMetric.observations(prs)
        summary = CycleTimeMetric.summary(observations, total_prs=len(prs))

        sample = [
            {
                "pr_number": o.pr_number,
                "node_id": o.github_node_id,
                "repository": o.repository_name_with_owner,
                "cycle_time_seconds": o.cycle_time_seconds,
            }
            for o in observations[:10]
        ]

        latest_collected: datetime | None = None
        for p in prs:
            if latest_collected is None or p.collected_at > latest_collected:
                latest_collected = p.collected_at

        return MetricSummaryResult(
            metric_id=CycleTimeMetric.metric_id,
            metric_version=CycleTimeMetric.metric_version,
            metric_name="pr_cycle_time",
            repository=repository,
            total_evaluated=len(prs),
            merged_count=len(observations),
            summary_stats=summary,
            observations_sample=sample,
            data_freshness_utc=latest_collected.isoformat() if latest_collected else None,
        )

    def query_monthly_stats(
        self,
        repository: str | None = None,
        months: int = 12,
        by_repo: bool = False,
        by_author: bool = False,
        include_bots: bool = True,
    ) -> list[MonthlyPRStats]:
        prs = self._load_canonical_prs(repository=repository)
        return MonthlyStatsMetric.calculate(
            prs=prs,
            months=months,
            by_repo=by_repo,
            by_author=by_author,
            include_bots=include_bots,
        )

    def compare_cohorts(
        self,
        cohort_a_repo: str,
        cohort_b_repo: str,
    ) -> CohortComparisonResult:
        res_a = self.query_pr_cycle_time(repository=cohort_a_repo)
        res_b = self.query_pr_cycle_time(repository=cohort_b_repo)

        p50_a = res_a.summary_stats.get("p50_seconds")
        p50_b = res_b.summary_stats.get("p50_seconds")
        mean_a = res_a.summary_stats.get("mean_seconds")
        mean_b = res_b.summary_stats.get("mean_seconds")

        delta_p50 = (p50_b - p50_a) if (p50_a is not None and p50_b is not None) else None
        delta_mean = (mean_b - mean_a) if (mean_a is not None and mean_b is not None) else None

        return CohortComparisonResult(
            metric_id=CycleTimeMetric.metric_id,
            metric_version=CycleTimeMetric.metric_version,
            cohort_a_name=cohort_a_repo,
            cohort_b_name=cohort_b_repo,
            cohort_a_count=res_a.total_evaluated,
            cohort_b_count=res_b.total_evaluated,
            cohort_a_stats=res_a.summary_stats,
            cohort_b_stats=res_b.summary_stats,
            delta_p50_seconds=delta_p50,
            delta_mean_seconds=delta_mean,
            methodology=(
                "Pure Python deterministic percentile calculation (linear rank interpolation)."
            ),
        )
