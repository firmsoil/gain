from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from gain.model.issue import SourceSystem


class DeploymentEnvironment(StrEnum):
    PRODUCTION = "production"
    STAGING = "staging"
    DEVELOPMENT = "development"
    CANARY = "canary"


class DeploymentStatus(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    IN_PROGRESS = "in_progress"
    CANCELLED = "cancelled"


class CanonicalDeployment(BaseModel):
    """Canonical domain entity representing a software deployment event."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(description="Global deployment identifier, e.g. 'gh_actions:run_101'")
    source_system: SourceSystem = SourceSystem.CUSTOM
    repository_name_with_owner: str
    environment: DeploymentEnvironment = DeploymentEnvironment.PRODUCTION
    status: DeploymentStatus = DeploymentStatus.SUCCESS
    commit_sha: str
    ref_name: str | None = None
    deployed_by: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
    duration_seconds: float | None = Field(default=None, ge=0)
    collected_at: datetime
    ingestion_run_id: str

    @field_validator("started_at", "completed_at", "collected_at", mode="after")
    @classmethod
    def ensure_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @property
    def is_production(self) -> bool:
        return self.environment == DeploymentEnvironment.PRODUCTION

    @property
    def is_failure(self) -> bool:
        return self.status == DeploymentStatus.FAILURE

    @property
    def is_success(self) -> bool:
        return self.status == DeploymentStatus.SUCCESS

    def calculate_duration(self) -> float | None:
        if self.duration_seconds is not None:
            return self.duration_seconds
        if self.completed_at is not None:
            return max(0.0, (self.completed_at - self.started_at).total_seconds())
        return None

    def to_record(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source_system": str(self.source_system.value),
            "repository_name_with_owner": self.repository_name_with_owner,
            "environment": str(self.environment.value),
            "status": str(self.status.value),
            "commit_sha": self.commit_sha,
            "ref_name": self.ref_name,
            "deployed_by": self.deployed_by,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_seconds": self.calculate_duration(),
            "collected_at": self.collected_at,
            "ingestion_run_id": self.ingestion_run_id,
        }
