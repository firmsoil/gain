from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CanonicalCommit(BaseModel):
    """Canonical domain entity representing a git commit."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sha: str = Field(description="Git commit hash")
    repository_name_with_owner: str
    author_name: str
    author_email: str | None = None
    author_login: str | None = None
    committed_at: datetime
    message: str
    additions: int | None = Field(default=None, ge=0)
    deletions: int | None = Field(default=None, ge=0)
    files_changed: int | None = Field(default=None, ge=0)
    collected_at: datetime
    ingestion_run_id: str

    @field_validator("committed_at", "collected_at", mode="after")
    @classmethod
    def ensure_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def to_record(self) -> dict[str, Any]:
        return {
            "sha": self.sha,
            "repository_name_with_owner": self.repository_name_with_owner,
            "author_name": self.author_name,
            "author_email": self.author_email,
            "author_login": self.author_login,
            "committed_at": self.committed_at,
            "message": self.message,
            "additions": self.additions,
            "deletions": self.deletions,
            "files_changed": self.files_changed,
            "collected_at": self.collected_at,
            "ingestion_run_id": self.ingestion_run_id,
        }
