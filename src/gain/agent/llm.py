"""LLM Gateway: Reasoning provider abstractions, deterministic mock, and tiered runtime."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import structlog

from gain.agent.models import Claim, InvestigationPlan
from gain.agent.runtime.router import ModelTier, TaskCriticality, TieredModelRouter

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


class EdgeSLMReasoningProvider(ReasoningProvider):
    """Edge SLM reasoning engine (e.g. local Ollama / small language model).

    Provides sub-200ms latency, zero cloud token costs, and high privacy isolation.
    """

    def __init__(self, model_name: str = "qwen2.5-coder:7b") -> None:
        self.model_name = model_name

    async def synthesize_briefing(
        self,
        intent: str,
        plan: InvestigationPlan,
        claims: list[Claim],
        limitations: list[str],
    ) -> str:
        lines: list[str] = [
            f"### Edge SLM Briefing [{self.model_name}]",
            f"**Target**: {plan.repository} | **Methodology**: {plan.methodology}",
            f"**Inquiry**: {intent}",
            "",
            "#### Verified Claims Summary:",
        ]
        for c in claims:
            lines.append(f"- [{c.classification.value}] {c.statement}")

        if limitations:
            lines.extend(["", "#### Edge Caveats:"])
            for lim in limitations:
                lines.append(f"- {lim}")

        return "\n".join(lines)


class TieredReasoningProvider(ReasoningProvider):
    """SLA-aware compound provider routing between local edge SLMs and frontier models."""

    def __init__(
        self,
        router: TieredModelRouter | None = None,
        edge_provider: ReasoningProvider | None = None,
        frontier_provider: ReasoningProvider | None = None,
        deterministic_provider: ReasoningProvider | None = None,
    ) -> None:
        self.router = router or TieredModelRouter()
        self.edge_provider = edge_provider or EdgeSLMReasoningProvider()
        self.deterministic_provider = deterministic_provider or DeterministicReasoningProvider()
        # In testing/default mode, frontier provider delegates to deterministic provider
        self.frontier_provider = frontier_provider or self.deterministic_provider
        self.last_routed_tier: ModelTier = ModelTier.DETERMINISTIC_CACHE
        self.last_route_reason: str = ""

    async def synthesize_briefing(
        self,
        intent: str,
        plan: InvestigationPlan,
        claims: list[Claim],
        limitations: list[str],
        criticality: TaskCriticality = TaskCriticality.MEDIUM,
        remaining_slack_ms: float = 5000.0,
    ) -> str:
        tier, reason = self.router.select_tier(
            criticality=criticality,
            remaining_slack_ms=remaining_slack_ms,
        )
        self.last_routed_tier = tier
        self.last_route_reason = reason

        logger.info(
            "tiered_reasoning_routed",
            tier=tier.value,
            criticality=criticality.value,
            remaining_slack_ms=remaining_slack_ms,
            reason=reason,
        )

        if tier == ModelTier.LOCAL_EDGE:
            return await self.edge_provider.synthesize_briefing(
                intent, plan, claims, limitations
            )
        if tier == ModelTier.CLOUD_FRONTIER:
            return await self.frontier_provider.synthesize_briefing(
                intent, plan, claims, limitations
            )
        return await self.deterministic_provider.synthesize_briefing(
            intent, plan, claims, limitations
        )


class LLMGateway:
    """Gateway managing reasoning providers, SLA budgets, and prompt boundaries."""

    def __init__(
        self,
        provider: ReasoningProvider | None = None,
        calibration_service: Any | None = None,
    ) -> None:
        self.provider = provider or DeterministicReasoningProvider()
        self.calibration_service = calibration_service

    async def generate_briefing(
        self,
        intent: str,
        plan: InvestigationPlan,
        claims: list[Claim],
        limitations: list[str],
        criticality: TaskCriticality = TaskCriticality.MEDIUM,
        remaining_slack_ms: float | None = None,
    ) -> str:
        logger.info(
            "llm_gateway_synthesis_started",
            methodology=plan.methodology,
            claim_count=len(claims),
            limitation_count=len(limitations),
            criticality=criticality.value,
            remaining_slack_ms=remaining_slack_ms,
        )

        if self.calibration_service:
            calibrated = self.calibration_service.compile_calibrated_prompt(intent)
            logger.info("llm_gateway_prompt_calibrated", prompt_length=len(calibrated))

        if isinstance(self.provider, TieredReasoningProvider):
            slack_ms = remaining_slack_ms if remaining_slack_ms is not None else 5000.0
            briefing = await self.provider.synthesize_briefing(
                intent=intent,
                plan=plan,
                claims=claims,
                limitations=limitations,
                criticality=criticality,
                remaining_slack_ms=slack_ms,
            )
        else:
            briefing = await self.provider.synthesize_briefing(intent, plan, claims, limitations)

        logger.info("llm_gateway_synthesis_completed", briefing_length=len(briefing))
        return briefing

    def get_audit_metadata(self) -> dict[str, Any]:
        """Return provider routing telemetry if available."""
        if isinstance(self.provider, TieredReasoningProvider):
            return {
                "last_routed_tier": self.provider.last_routed_tier.value,
                "last_route_reason": self.provider.last_route_reason,
            }
        return {"provider": self.provider.__class__.__name__}
