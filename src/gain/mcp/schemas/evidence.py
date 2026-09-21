"""Structured schema for evidence packages."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class EvidencePackageResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence_id: str
    claim: str
    claim_classification: str
    metric_id: str
    metric_version: int
    population_count: int
    time_window: str
    data_freshness_utc: str | None
    statistical_method: str
    assumptions: list[str]
    limitations: list[str]
    confidence_level: str
    source_references: list[str]
    supporting_artifacts: list[str]
