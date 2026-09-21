"""Structured schema for metric and entity lineage."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LineageStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    layer: str = Field(description="raw, canonical, or metric_observation")
    identifier: str
    metadata: dict[str, Any]


class LineageResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_id: str
    target_type: str
    provenance_chain: list[str]
    steps: list[LineageStep]
