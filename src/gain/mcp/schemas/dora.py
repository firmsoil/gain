"""Structured schema for DORA metrics."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DORAMetricItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metric_name: str  # change_lead_time, deployment_frequency, etc.
    status: str  # "available", "insufficient_data", "unsupported"
    value: float | None = None
    unit: str | None = None
    metric_version: int = 1
    notes: str | None = None


class DORAMetricsResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str = Field(description="OVERALL status: available, insufficient_data, unsupported")
    population: str
    time_window: str
    change_lead_time: DORAMetricItem
    deployment_frequency: DORAMetricItem
    failed_deployment_recovery_time: DORAMetricItem
    change_fail_rate: DORAMetricItem
    deployment_rework_rate: DORAMetricItem
    data_freshness_utc: str | None = None
    data_quality_summary: str | None = None
    missing_dependencies: list[str] = Field(
        default_factory=list,
        description=(
            "Dependencies required to calculate full DORA metrics (e.g. deployments, incidents)"
        ),
    )
