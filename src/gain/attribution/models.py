"""Domain models for in-tree AI attribution detection and telemetry synthesis."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from gain.mcp.schemas.ai import ClaimClassification
from gain.model.ai import AiToolType


class AttributionSignalType(StrEnum):
    """Categorization of observable AI attribution signal sources."""

    TRAILER = "git_trailer"
    BOT_AUTHOR = "bot_author"
    PR_LABEL = "pr_label"
    PR_BODY = "pr_body"
    COMMIT_MESSAGE = "commit_message"
    CODE_METADATA = "code_metadata"


class AttributionSignal(BaseModel):
    """An individual piece of verifiable evidence indicating AI tooling usage."""

    model_config = ConfigDict(frozen=True)

    signal_type: AttributionSignalType
    tool_type: AiToolType
    confidence: float = Field(ge=0.0, le=1.0)
    source_identifier: str  # e.g. "commit:abc1234" or "pr_author:copilot[bot]"
    evidence_text: str


class AttributionReport(BaseModel):
    """Comprehensive AI attribution audit summary for an engineering repository."""

    model_config = ConfigDict(frozen=True)

    repository: str
    total_prs: int = 0
    ai_assisted_prs: int = 0
    total_commits: int = 0
    ai_assisted_commits: int = 0
    ai_penetration_rate: float = 0.0
    detected_tools: list[AiToolType] = Field(default_factory=list)
    ai_active_developers: list[str] = Field(default_factory=list)
    signals: list[AttributionSignal] = Field(default_factory=list)
    epistemic_classification: ClaimClassification = ClaimClassification.OBSERVED
