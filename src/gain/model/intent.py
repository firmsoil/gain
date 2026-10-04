"""Canonical domain entity for Intent Archiving (SE 3.0 specification IP).

In SE 3.0, the core intellectual property and development driver is the
co-constructed human-AI conversation and intent specification, rather than
ephemeral generated code artifacts (Hassan et al. 2026).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class IntentSpeaker(StrEnum):
    """Participant in the intent elicitation dialogue."""

    HUMAN = "human"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ClarificationType(StrEnum):
    """Categorization of clarification turns during intent alignment."""

    GOAL_REFINEMENT = "goal_refinement"
    CONSTRAINT = "constraint"
    EXAMPLE = "example"
    ACCEPTANCE_CRITERIA = "acceptance_criteria"
    AMBIGUITY_RESOLVED = "ambiguity_resolved"


class IntentStatus(StrEnum):
    """Lifecycle status of a specification intent."""

    DRAFT = "draft"
    ALIGNING = "aligning"
    ALIGNED = "aligned"
    SYNTHESIZING = "synthesizing"
    VERIFIED = "verified"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class EpistemicTier(StrEnum):
    """Authoritative epistemic claim grounding classification."""

    OBSERVED = "Observed"
    DERIVED = "Derived"
    ASSOCIATED = "Associated"
    ATTRIBUTED = "Attributed"
    MODELED = "Modeled"
    ASSUMED = "Assumed"
    UNKNOWN = "Unknown"


class IntentTurn(BaseModel):
    """An individual dialogue turn during conversational intent alignment."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    speaker: IntentSpeaker
    content: str
    timestamp: datetime
    clarification_type: ClarificationType | None = None

    @field_validator("timestamp", mode="after")
    @classmethod
    def ensure_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def to_record(self) -> dict[str, Any]:
        return {
            "speaker": str(self.speaker.value),
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "clarification_type": (
                str(self.clarification_type.value) if self.clarification_type else None
            ),
        }


class CanonicalIntent(BaseModel):
    """Canonical, transport-independent domain entity representing a development intent.

    Acts as the authoritative version-controlled specification asset in SE 3.0.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(description="Unique intent identifier, e.g. 'intent-f8a12bc'")
    repository: str = Field(description="Repository name with owner, e.g. 'firmsoil/gain'")
    author_id: str = Field(description="Author identifier (human developer or agent)")
    title: str = Field(description="High-level goal title")
    raw_prompt: str = Field(description="Initial raw prompt articulated by the human")
    aligned_specification: str | None = Field(
        default=None,
        description="Co-constructed formal specification post-alignment",
    )
    acceptance_criteria: list[str] = Field(
        default_factory=list,
        description="Explicit acceptance conditions derived prior to synthesis",
    )
    synthesized_test_identifiers: list[str] = Field(
        default_factory=list,
        description="Tests compiled strictly from intents (Compiler.next invariant)",
    )
    dialogue_history: list[IntentTurn] = Field(
        default_factory=list,
        description="Sequential conversational turns during alignment",
    )
    status: IntentStatus = IntentStatus.DRAFT
    epistemic_tier: EpistemicTier = EpistemicTier.OBSERVED
    linked_pr_numbers: list[int] = Field(default_factory=list)
    linked_issue_keys: list[str] = Field(default_factory=list)
    created_at: datetime
    aligned_at: datetime | None = None
    collected_at: datetime
    ingestion_run_id: str

    @field_validator("created_at", "aligned_at", "collected_at", mode="after")
    @classmethod
    def ensure_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @property
    def is_aligned(self) -> bool:
        return self.status == IntentStatus.ALIGNED or self.aligned_at is not None

    @property
    def turn_count(self) -> int:
        return len(self.dialogue_history)

    def alignment_duration_seconds(self) -> float | None:
        """Elapsed time in seconds from initial prompt to specification alignment."""
        if self.aligned_at is None:
            return None
        return max(0.0, (self.aligned_at - self.created_at).total_seconds())

    def to_record(self) -> dict[str, Any]:
        """Flatten model to a dictionary suitable for columnar Parquet persistence."""
        return {
            "id": self.id,
            "repository": self.repository,
            "author_id": self.author_id,
            "title": self.title,
            "raw_prompt": self.raw_prompt,
            "aligned_specification": self.aligned_specification,
            "acceptance_criteria": self.acceptance_criteria,
            "synthesized_test_identifiers": self.synthesized_test_identifiers,
            "dialogue_history_json": json.dumps([t.to_record() for t in self.dialogue_history]),
            "status": str(self.status.value),
            "epistemic_tier": str(self.epistemic_tier.value),
            "linked_pr_numbers": self.linked_pr_numbers,
            "linked_issue_keys": self.linked_issue_keys,
            "created_at": self.created_at,
            "aligned_at": self.aligned_at,
            "collected_at": self.collected_at,
            "ingestion_run_id": self.ingestion_run_id,
        }
