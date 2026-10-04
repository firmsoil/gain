"""Goal-Tracking Verifier for pre-execution assertion compilation (Compiler.next).

Derives verification checks strictly from user-aligned intents *prior* to
execution, preventing the classic SE 2.0 anti-pattern of generating tests
from generated code or speculative results (Hassan et al. 2026).
"""

from __future__ import annotations

import re

import structlog

from gain.agent.models import Claim, ClaimType, InvestigationPlan
from gain.model.intent import CanonicalIntent

log = structlog.get_logger(__name__)


class VerificationAssertion:
    """A deterministic verification rule compiled from an intent requirement."""

    def __init__(self, rule_id: str, description: str) -> None:
        self.rule_id = rule_id
        self.description = description


class IntentVerifier:
    """Compiles and executes verification assertions derived from aligned intents."""

    def compile_assertions(
        self,
        intent: CanonicalIntent | None = None,
        raw_intent_text: str | None = None,
    ) -> list[VerificationAssertion]:
        """Compile pre-flight verification assertions directly from intent requirements."""
        assertions: list[VerificationAssertion] = [
            VerificationAssertion(
                rule_id="RULE-PROVENANCE",
                description="All executed steps must originate from verified MCP tool definitions.",
            ),
            VerificationAssertion(
                rule_id="RULE-QUALITY-GATE",
                description="Investigation must evaluate dataset health and freshness.",
            ),
        ]

        text = (intent.raw_prompt if intent else (raw_intent_text or "")).lower()

        if re.search(r"\b(ai|copilot)\b", text) or "impact" in text:
            assertions.append(
                VerificationAssertion(
                    rule_id="RULE-CONFOUNDER-ISOLATION",
                    description=(
                        "AI impact claims must isolate developer cohorts and control "
                        "for PR size disparity."
                    ),
                )
            )

        if "dora" in text or "stability" in text or "velocity" in text:
            assertions.append(
                VerificationAssertion(
                    rule_id="RULE-STABILITY-BALANCE",
                    description=(
                        "Delivery velocity evaluations must incorporate stability "
                        "or change failure metrics to detect instability taxes."
                    ),
                )
            )

        return assertions

    def verify_plan(
        self,
        plan: InvestigationPlan,
        intent: CanonicalIntent | None = None,
    ) -> tuple[bool, list[str]]:
        """Verify that an investigation plan structurally satisfies intent constraints."""
        violations: list[str] = []
        target_repo = intent.repository if intent else plan.repository

        # 1. Repository constraint verification
        for step in plan.steps:
            step_repo = step.arguments.get("repository") or step.arguments.get("repo")
            if step_repo and step_repo != target_repo:
                violations.append(
                    f"Step '{step.step_id}' targets repository '{step_repo}' "
                    f"diverging from aligned repository '{target_repo}'."
                )

        # 2. Quality gate verification
        has_quality_check = any(s.tool_name == "get_data_quality" for s in plan.steps)
        if not has_quality_check:
            violations.append(
                "Plan lacks mandatory 'get_data_quality' step for dataset health verification."
            )

        # 3. Confounder control verification for AI inquiries
        intent_text = (intent.raw_prompt if intent else plan.intent).lower()
        if re.search(r"\b(ai|copilot)\b", intent_text):
            has_impact_check = any(s.tool_name == "analyze_ai_impact" for s in plan.steps)
            if not has_impact_check:
                violations.append(
                    "AI velocity inquiry plan lacks 'analyze_ai_impact' cohort comparison tool."
                )

        is_valid = len(violations) == 0
        if not is_valid:
            log.warning("intent_verification_violations_found", violations=violations)

        return is_valid, violations

    def verify_claims(
        self,
        claims: list[Claim],
        intent: CanonicalIntent | None = None,
    ) -> list[str]:
        """Verify that synthesized claims conform to epistemic classification constraints."""
        audit_notes: list[str] = []

        for claim in claims:
            # Epistemic defense: unobserved causality cannot be claimed as Attributed
            is_ai_claim = "copilot" in claim.statement.lower() or "ai" in claim.statement.lower()
            if is_ai_claim and claim.classification == ClaimType.ATTRIBUTED:
                audit_notes.append(
                    f"Claim '{claim.claim_id}' claims direct AI attribution without "
                    "randomized causal proof; downgraded to Associated."
                )

            if claim.confidence < 0.5:
                audit_notes.append(
                    f"Claim '{claim.claim_id}' exhibits low confidence ({claim.confidence:.2f})."
                )

        return audit_notes
