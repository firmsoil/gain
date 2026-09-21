"""Structured schemas for engineering metrics and metric definitions."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MetricObservationSample(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pr_number: int
    node_id: str
    repository: str
    cycle_time_seconds: float


class MetricResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metric_id: str = Field(description="Authoritative metric ID from Metric Catalog")
    metric_version: int = Field(description="Metric definition version")
    metric_name: str
    repository: str | None = None
    time_window: str | None = None
    population_count: int = Field(description="Total entities evaluated")
    merged_count: int | None = Field(default=None, description="Number of merged PRs evaluated")
    summary_stats: dict[str, float | int | None] = Field(
        description="Statistical distribution (p50, p75, p90, p95, mean, count)"
    )
    observations_sample: list[dict[str, Any]] = Field(default_factory=list)
    data_freshness_utc: str | None = None
    provenance_source: str = "GAIN Local Parquet Store"


class MetricComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metric_id: str
    metric_version: int
    cohort_a_name: str
    cohort_b_name: str
    cohort_a_count: int
    cohort_b_count: int
    cohort_a_stats: dict[str, float | int | None]
    cohort_b_stats: dict[str, float | int | None]
    delta_p50_seconds: float | None = None
    delta_mean_seconds: float | None = None
    comparison_methodology: str


class CohortResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cohort_id: str
    cohort_definition: dict[str, Any]
    population_count: int
    metric_results: list[MetricResult]


class MetricDefinitionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metric_id: str
    metric_version: int
    name: str
    category: str
    type: str
    availability: str
    executive: bool
    formula: str
    source_fields: list[str]
    grain: str
    unit: str
    statistics: list[str] | None = None
    filters: list[str] | None = None
    null_policy: str | None = None
    interpretation: str | None = None
    gaming_risk: str | None = None
