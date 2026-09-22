from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PullRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    github_node_id: str
    number: int = Field(gt=0)
    repository_name_with_owner: str
    repository_id: str
    author_login: str | None = None
    author_type: str | None = None
    created_at: datetime
    closed_at: datetime | None = None
    merged_at: datetime | None = None
    state: str
    is_draft: bool
    additions: int | None = Field(default=None, ge=0)
    deletions: int | None = Field(default=None, ge=0)
    changed_files: int | None = Field(default=None, ge=0)
    review_decision: str | None = None
    collected_at: datetime
    ingestion_run_id: str

    @field_validator("created_at", "closed_at", "merged_at", "collected_at", mode="after")
    @classmethod
    def ensure_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @field_validator("state")
    @classmethod
    def validate_state(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in {"OPEN", "CLOSED", "MERGED"}:
            raise ValueError(f"Unsupported pull request state: {value}")
        return normalized

    @property
    def is_bot(self) -> bool:
        return self.author_type == "Bot"

    @property
    def merged(self) -> bool:
        return self.merged_at is not None

    def to_record(self) -> dict[str, Any]:
        return {
            "github_node_id": self.github_node_id,
            "number": self.number,
            "repository_name_with_owner": self.repository_name_with_owner,
            "repository_id": self.repository_id,
            "author_login": self.author_login,
            "author_type": self.author_type,
            "created_at": self.created_at,
            "closed_at": self.closed_at,
            "merged_at": self.merged_at,
            "state": self.state,
            "is_draft": self.is_draft,
            "additions": self.additions,
            "deletions": self.deletions,
            "changed_files": self.changed_files,
            "review_decision": self.review_decision,
            "collected_at": self.collected_at,
            "ingestion_run_id": self.ingestion_run_id,
        }
