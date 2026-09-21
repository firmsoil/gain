"""LLM Gateway: Reasoning provider abstractions, deterministic mock, and prompt synthesis."""

from __future__ import annotations

from abc import ABC, abstractmethod

import structlog

from gain.agent.models import Claim, InvestigationPlan

logger = structlog.get_logger(__name__)


class ReasoningProvider(ABC):
    """Abstract interface for LLM reasoning and interpretive synthesis."""

    @abstractmethod
    async def synthesize_briefing(
        self,
        intent: str,
        plan: InvestigationPlan,
        claims: list[Claim],
        limitations: list[str],
    ) -> str:
        """Synthesize an interpretive summary strictly grounded in claims."""


class DeterministicReasoningProvider(ReasoningProvider):
    """Deterministic, zero-token reasoning engine for reproducible CI and offline evaluation."""

    async def synthesize_briefing(
        self,
        intent: str,
        plan: InvestigationPlan,
        claims: list[Claim],
        limitations: list[str],
    ) -> str:
        lines: list[str] = [
            "### Engineering Intelligence Investigation Briefing",
            f"**Inquiry**: {intent}",
            f"**Repository**: {plan.repository}",
            f"**Methodology**: {plan.methodology}",
            "",
            "#### Core Findings & Classified Claims:",
        ]

        for claim in claims:
            lines.append(f"- **[{claim.classification.value}]** {claim.statement}")

        if limitations:
            lines.extend(["", "#### Investigation Constraints & Limitations:"])
            for lim in limitations:
                lines.append(f"- *{lim}*")

        lines.extend(
            [
                "",
                "#### Interpretive Conclusion:",
                (
                    "All reported metrics and cohort comparisons derive from deterministic "
                    "GAIN canonical calculations."
                ),
                (
                    "In accordance with GAIN architecture standards, non-observed phenomena "
                    "(such as direct AI causality) are strictly classified as "
                    "Associated or Unknown."
                ),
            ]
        )

        return "\n".join(lines)


class LLMGateway:
    """Gateway managing reasoning providers, prompt boundaries, and audit telemetry."""

    def __init__(self, provider: ReasoningProvider | None = None) -> None:
        self.provider = provider or DeterministicReasoningProvider()

    async def generate_briefing(
        self,
        intent: str,
        plan: InvestigationPlan,
        claims: list[Claim],
        limitations: list[str],
    ) -> str:
        logger.info(
            "llm_gateway_synthesis_started",
            methodology=plan.methodology,
            claim_count=len(claims),
            limitation_count=len(limitations),
        )
        briefing = await self.provider.synthesize_briefing(intent, plan, claims, limitations)
        logger.info("llm_gateway_synthesis_completed", briefing_length=len(briefing))
        return briefing
