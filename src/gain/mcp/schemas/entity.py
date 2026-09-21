"""Structured schema for canonical entities exposed via MCP."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class CanonicalEntityResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity_type: str = "PullRequest"
    identifier: str
    repository: str
    number: int
    state: str
    is_draft: bool
    author_login: str | None
    created_at_utc: str
    closed_at_utc: str | None
    merged_at_utc: str | None
    cycle_time_seconds: float | None
    additions: int | None
    deletions: int | None
    changed_files: int | None
    provenance: dict[str, Any]
