"""Structured schemas for AI impact analysis and economic ROI modeling."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ClaimClassification(StrEnum):
    OBSERVED = "Observed"
    DERIVED = "Derived"
    ASSOCIATED = "Associated"
    ATTRIBUTED = "Attributed"
    MODELED = "Modeled"
    ASSUMED = "Assumed"
    UNKNOWN = "Unknown"


class AIImpactResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str = Field(description="'available' or 'insufficient_data'")
    classification: ClaimClassification
    attribution_source: str | None = None
    attribution_method: str | None = None
    cohort_definition: dict[str, Any]
    comparison_cohort: dict[str, Any] | None = None
    confidence_level: str
    limitations: list[str]
    findings: list[str] = Field(default_factory=list)
    missing_dependencies: list[str] = Field(
        default_factory=list,
        description="Required data assets not yet available (e.g. telemetry tags, IDE telemetry)",
    )


class ROIScenarioResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str = Field(description="'available' or 'unsupported_capability'")
    is_modeled: bool = True
    model_version: str = "gain-roi-v1"
    time_period: str
    population: str
    investment_cost: float | None = None
    economic_value_components: dict[str, float] = Field(default_factory=dict)
    net_benefit: float | None = None
    roi_percentage: float | None = None
    assumptions: list[str] = Field(default_factory=list)
    attribution_basis: str | None = None
    sensitivity_analysis: dict[str, Any] = Field(default_factory=dict)
    uncertainty_range: dict[str, float] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
