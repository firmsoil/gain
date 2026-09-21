"""Domain model for authoritative AI developer adoption and usage telemetry."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, computed_field


class AiToolType(StrEnum):
    """Categorization of AI coding tools."""

    COPILOT = "copilot"
    CURSOR = "cursor"
    CLAUDE_DEV = "claude_dev"
    OTHER = "other"


class AiDeveloperTelemetry(BaseModel):
    """Immutable record of developer-level AI adoption and activity metrics."""

    model_config = ConfigDict(frozen=True)

    developer_id: str
    repository: str
    tool_type: AiToolType = AiToolType.COPILOT
    window_start: datetime = Field(default_factory=lambda: datetime(2026, 1, 1, tzinfo=UTC))
    window_end: datetime = Field(default_factory=lambda: datetime(2026, 2, 1, tzinfo=UTC))
    active_days: int = Field(default=20, ge=0, le=366)
    suggestions_count: int = Field(default=0, ge=0)
    acceptances_count: int = Field(default=0, ge=0)
    lines_suggested: int = Field(default=0, ge=0)
    lines_accepted: int = Field(default=0, ge=0)
    is_ai_active: bool = True

    @computed_field  # type: ignore[prop-decorator]
    @property
    def acceptance_rate(self) -> float:
        """Percentage of AI code suggestions accepted by developer."""
        if self.suggestions_count <= 0:
            return 0.0
        return round(self.acceptances_count / self.suggestions_count, 4)
