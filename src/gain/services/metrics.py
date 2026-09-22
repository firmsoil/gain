"""Domain service for deterministic engineering metrics and Metric Catalog lookups."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl
import structlog

from gain.config import Settings, get_settings
from gain.metrics.catalog import MetricCatalog
from gain.metrics.cycle_time import CycleTimeMetric
from gain.metrics.monthly_stats import MonthlyPRStats, MonthlyStatsMetric
from gain.model.pr import PullRequest
from gain.storage.analytics import read_canonical, scan_canonical

log = structlog.get_logger(__name__)


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

    def _scan_canonical_prs(self, repository: str | None = None) -> pl.LazyFrame:
        """Scan canonical PR dataset returning a LazyFrame with repository filter pushed down."""
        lf = scan_canonical(self.settings.canonical_dir, entity_type="pull_request")
        if repository:
            lf = lf.filter(pl.col("repository_name_with_owner") == repository)
        return lf

    def query_pr_cycle_time(
        self,
        repository: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> MetricSummaryResult:
        lf = self._scan_canonical_prs(repository=repository)
        if start_date:
            start_utc = (
                start_date if start_date.tzinfo is not None else start_date.replace(tzinfo=UTC)
            )
            lf = lf.filter(pl.col("created_at") >= start_utc)
        if end_date:
            end_utc = end_date if end_date.tzinfo is not None else end_date.replace(tzinfo=UTC)
            lf = lf.filter(pl.col("created_at") <= end_utc)

        # 1. Total evaluated count and freshness across all matching PRs
        meta_df = lf.select(
            [
                pl.len().alias("total_evaluated"),
                pl.col("collected_at").max().alias("latest_collected"),
            ]
        ).collect()
        total_evaluated = int(meta_df["total_evaluated"][0]) if len(meta_df) > 0 else 0
        latest_raw = meta_df["latest_collected"][0] if len(meta_df) > 0 else None
        data_freshness_utc: str | None = latest_raw.isoformat() if latest_raw is not None else None

        # 2. Cycle time in seconds for merged PRs with valid duration
        cycle_time_expr = (
            pl.col("merged_at") - pl.col("created_at")
        ).dt.total_microseconds() / 1_000_000.0
        merged_lf = (
            lf.filter(pl.col("merged_at").is_not_null())
            .with_columns(cycle_time_expr.alias("cycle_time_seconds"))
            .filter(pl.col("cycle_time_seconds") >= 0.0)
        )

        # 3. Aggregation summary statistics via Polars
        ct_col = pl.col("cycle_time_seconds")
        stats_df = merged_lf.select(
            [
                pl.len().alias("merged_count"),
                ct_col.quantile(0.50, interpolation="linear").alias("p50_seconds"),
                ct_col.quantile(0.75, interpolation="linear").alias("p75_seconds"),
                ct_col.quantile(0.90, interpolation="linear").alias("p90_seconds"),
                ct_col.quantile(0.95, interpolation="linear").alias("p95_seconds"),
                ct_col.mean().alias("mean_seconds"),
            ]
        ).collect()

        merged_count = int(stats_df["merged_count"][0]) if len(stats_df) > 0 else 0

        summary: dict[str, float | int | None] = {
            "count": merged_count,
            "merged_count": merged_count,
            "total_evaluated": total_evaluated,
            "p50_seconds": stats_df["p50_seconds"][0] if merged_count > 0 else None,
            "p75_seconds": stats_df["p75_seconds"][0] if merged_count > 0 else None,
            "p90_seconds": stats_df["p90_seconds"][0] if merged_count > 0 else None,
            "p95_seconds": stats_df["p95_seconds"][0] if merged_count > 0 else None,
            "mean_seconds": stats_df["mean_seconds"][0] if merged_count > 0 else None,
        }

        # 4. First 10 observations sample
        sample_df = (
            merged_lf.select(
                [
                    pl.col("number").alias("pr_number"),
                    pl.col("github_node_id").alias("node_id"),
                    pl.col("repository_name_with_owner").alias("repository"),
                    pl.col("cycle_time_seconds"),
                ]
            )
            .limit(10)
            .collect()
        )
        sample = sample_df.to_dicts()

        return MetricSummaryResult(
            metric_id=CycleTimeMetric.metric_id,
            metric_version=CycleTimeMetric.metric_version,
            metric_name="pr_cycle_time",
            repository=repository,
            total_evaluated=total_evaluated,
            merged_count=merged_count,
            summary_stats=summary,
            observations_sample=sample,
            data_freshness_utc=data_freshness_utc,
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
