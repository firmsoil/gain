from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SourceSystem(StrEnum):
    JIRA = "jira"
    LINEAR = "linear"
    GITHUB = "github"
    GITLAB = "gitlab"
    CUSTOM = "custom"


class IssueType(StrEnum):
    STORY = "story"
    BUG = "bug"
    TASK = "task"
    EPIC = "epic"
    SUBTASK = "subtask"
    OTHER = "other"


class IssueStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    DONE = "done"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class CanonicalIssue(BaseModel):
    """Canonical, transport-independent domain entity representing a work item."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(description="Global unique issue identifier, e.g. 'jira:PROJ-101'")
    key: str = Field(description="Human-readable issue key, e.g. 'PROJ-101'")
    source_system: SourceSystem
    project_key: str
    title: str
    description: str | None = None
    issue_type: IssueType = IssueType.TASK
    status: IssueStatus = IssueStatus.OPEN
    priority: str | None = None
    author: str | None = None
    assignee: str | None = None
    labels: list[str] = Field(default_factory=list)
    story_points: float | None = Field(default=None, ge=0)
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None
    due_date: datetime | None = None
    parent_id: str | None = None
    linked_pr_keys: list[str] = Field(default_factory=list)
    collected_at: datetime
    ingestion_run_id: str

    @field_validator(
        "created_at", "updated_at", "resolved_at", "due_date", "collected_at", mode="after"
    )
    @classmethod
    def ensure_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @property
    def is_resolved(self) -> bool:
        return self.status in {IssueStatus.DONE, IssueStatus.CLOSED} or self.resolved_at is not None

    def cycle_time_seconds(self) -> float | None:
        """Returns the elapsed resolution time in seconds from creation to resolution."""
        if self.resolved_at is None:
            return None
        return max(0.0, (self.resolved_at - self.created_at).total_seconds())

    def to_record(self) -> dict[str, Any]:
        """Flatten model to a dictionary suitable for columnar DataFrame persistence."""
        return {
            "id": self.id,
            "key": self.key,
            "source_system": str(self.source_system.value),
            "project_key": self.project_key,
            "title": self.title,
            "description": self.description,
            "issue_type": str(self.issue_type.value),
            "status": str(self.status.value),
            "priority": self.priority,
            "author": self.author,
            "assignee": self.assignee,
            "labels": self.labels,
            "story_points": self.story_points,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "resolved_at": self.resolved_at,
            "due_date": self.due_date,
            "parent_id": self.parent_id,
            "linked_pr_keys": self.linked_pr_keys,
            "collected_at": self.collected_at,
            "ingestion_run_id": self.ingestion_run_id,
        }
