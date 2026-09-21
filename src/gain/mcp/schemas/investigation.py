"""Structured schemas for durable investigations."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class InvestigationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    investigation_id: str
    plan_id: str
    title: str
    status: str
    analysis_version: str
    created_at_utc: str
    updated_at_utc: str
    evidence_references: list[str] = Field(default_factory=list)
    result_references: list[str] = Field(default_factory=list)


class InvestigationStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    investigation_id: str
    plan_id: str
    tenant_id: str
    principal_id: str
    title: str
    status: str
    analysis_version: str
    query_specification: dict[str, Any]
    created_at_utc: str
    updated_at_utc: str
    evidence_references: list[str] = Field(default_factory=list)
    result_references: list[str] = Field(default_factory=list)
