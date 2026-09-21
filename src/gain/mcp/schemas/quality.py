"""Structured schema for dataset quality reports."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DataQualityResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset_id: str
    total_records: int
    valid_records: int
    freshness_utc: str | None
    completeness_score: float = Field(description="Ratio of complete records [0.0 - 1.0]")
    validity_score: float = Field(
        description="Ratio of records passing integrity checks [0.0 - 1.0]"
    )
    source_status: str
    population_sufficiency: str
    known_gaps: list[str] = Field(default_factory=list)
    quality_flags: list[dict[str, Any]] = Field(default_factory=list)
