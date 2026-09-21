"""Domain models for GAIN Engineering Intelligence Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class ClaimType(StrEnum):
    """Authoritative 7-tier claim classification taxonomy."""

    OBSERVED = "Observed"
    DERIVED = "Derived"
    ASSOCIATED = "Associated"
    ATTRIBUTED = "Attributed"
    MODELED = "Modeled"
    ASSUMED = "Assumed"
    UNKNOWN = "Unknown"


class Claim(BaseModel):
    """An analytical or interpretive claim tagged with classification and provenance."""

    model_config = ConfigDict(frozen=True)

    claim_id: str = Field(default_factory=lambda: f"claim-{uuid4().hex[:8]}")
    statement: str
    classification: ClaimType
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source_refs: list[str] = Field(default_factory=list)
    metric_id: str | None = None
    lineage_ref: str | None = None
    notes: str | None = None


class PlanStepStatus(StrEnum):
    """Execution status of an investigation plan step."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class PlanStep(BaseModel):
    """A discrete, executable step in an investigation plan."""

    step_id: str
    description: str
    tool_name: str
    target_system: str  # "gain_mcp" | "github_mcp"
    arguments: dict[str, Any] = Field(default_factory=dict)
    dependencies: list[str] = Field(default_factory=list)
    status: PlanStepStatus = PlanStepStatus.PENDING
    output: dict[str, Any] | None = None
    error: str | None = None
    duration_ms: float = 0.0


class InvestigationPlan(BaseModel):
    """Structured, reproducible plan for investigating an engineering question."""

    plan_id: str = Field(default_factory=lambda: f"plan-{uuid4().hex[:8]}")
    investigation_id: str
    intent: str
    methodology: str
    repository: str
    steps: list[PlanStep] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def is_complete(self) -> bool:
        """Return True if all steps have reached a terminal state."""
        return all(
            step.status in (PlanStepStatus.COMPLETED, PlanStepStatus.FAILED, PlanStepStatus.SKIPPED)
            for step in self.steps
        )


class InvestigationContext(BaseModel):
    """Security and execution context established by the Agent Gateway."""

    model_config = ConfigDict(frozen=True)

    request_id: str = Field(default_factory=lambda: f"req-{uuid4().hex[:12]}")
    investigation_id: str = Field(default_factory=lambda: f"inv-{uuid4().hex[:12]}")
    tenant_id: str = "default"
    principal_id: str = "user-default"
    organization: str = "firmsoil"
    scopes: list[str] = Field(
        default_factory=lambda: ["gain:metrics:read", "gain:investigation:write"]
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AgentResponse(BaseModel):
    """Comprehensive, evidence-grounded response from the Engineering Intelligence Agent."""

    investigation_id: str
    request_id: str
    query: str
    summary: str
    plan: InvestigationPlan
    claims: list[Claim] = Field(default_factory=list)
    evidence_package_id: str | None = None
    data_freshness: str = "Near-real-time"
    limitations: list[str] = Field(default_factory=list)
    audit_events: list[dict[str, Any]] = Field(default_factory=list)
    status: str = "completed"
