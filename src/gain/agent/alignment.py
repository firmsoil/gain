"""Conversational Intent Alignment protocol (Teammate.next & IDE.next).

Implements multi-turn intent elicitation, ambiguity resolution, and
specification co-construction between human developers and AI teammates
(Hassan et al. 2026).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from uuid import uuid4

import structlog

from gain.agent.models import InvestigationContext
from gain.model.intent import (
    CanonicalIntent,
    ClarificationType,
    EpistemicTier,
    IntentSpeaker,
    IntentStatus,
    IntentTurn,
)

log = structlog.get_logger(__name__)


class AlignmentSession:
    """Manages iterative, multi-turn human-AI intent alignment before plan execution."""

    def __init__(
        self,
        session_id: str | None = None,
        context: InvestigationContext | None = None,
        max_turns: int = 3,
        default_repo: str = "firmsoil/gain",
    ) -> None:
        self.session_id = session_id or f"align-{uuid4().hex[:8]}"
        self.context = context or InvestigationContext()
        self.max_turns = max_turns
        self.default_repo = default_repo
        self.dialogue_history: list[IntentTurn] = []
        self.status: IntentStatus = IntentStatus.ALIGNING
        self.aligned_repo: str = default_repo
        self.raw_prompt: str = ""
        self.aligned_specification: str | None = None
        self.acceptance_criteria: list[str] = []
        self.created_at: datetime = datetime.now(UTC)
        self.aligned_at: datetime | None = None

    def process_turn(self, user_utterance: str) -> tuple[str, bool]:
        """Process a dialogue turn from the user.

        Returns:
            tuple[str, bool]: (assistant_response, is_fully_aligned)
        """
        now = datetime.now(UTC)
        if not self.raw_prompt:
            self.raw_prompt = user_utterance

        # Extract repository if present in utterance
        extracted_repo = self._extract_repository(user_utterance)
        if extracted_repo:
            self.aligned_repo = extracted_repo

        # Record human utterance
        human_turn = IntentTurn(
            speaker=IntentSpeaker.HUMAN,
            content=user_utterance,
            timestamp=now,
            clarification_type=ClarificationType.GOAL_REFINEMENT,
        )
        self.dialogue_history.append(human_turn)

        # Detect ambiguities across the conversation
        ambiguities = self._detect_ambiguities(user_utterance)
        turn_count = len(self.dialogue_history)

        # Alignment completion condition:
        # 1. No ambiguities remaining, OR
        # 2. User explicitly signals confirmation, OR
        # 3. Maximum turn limit reached (escape hatch)
        confirmation_signals = {"proceed", "yes", "confirm", "go ahead", "approved", "ok"}
        user_confirmed = any(sig in user_utterance.lower() for sig in confirmation_signals)

        if not ambiguities or user_confirmed or (turn_count >= self.max_turns * 2 - 1):
            return self._finalize_alignment(user_utterance, now)

        # Formulate next clarification question
        next_question, clarification_type = self._formulate_clarification(ambiguities[0])
        assistant_turn = IntentTurn(
            speaker=IntentSpeaker.ASSISTANT,
            content=next_question,
            timestamp=datetime.now(UTC),
            clarification_type=clarification_type,
        )
        self.dialogue_history.append(assistant_turn)
        return next_question, False

    def _detect_ambiguities(self, utterance: str) -> list[str]:
        ambiguities: list[str] = []
        full_text = " ".join(t.content.lower() for t in self.dialogue_history)

        # 1. Check for ambiguous causal claims
        causal_indicators = [
            "cause",
            "make us faster",
            "make our developers faster",
            "faster",
            "increase velocity",
        ]
        has_causal = any(term in full_text for term in causal_indicators)
        has_control = any(
            ctrl in full_text for ctrl in ["cohort", "baseline", "confound", "control"]
        )
        if has_causal and not has_control:
            ambiguities.append("uncontrolled_causality")

        # 2. Check repository specification
        if self._extract_repository(full_text) is None and "default" not in full_text:
            ambiguities.append("unspecified_repository")

        # 3. Check for vague time window
        has_vague_time = any(
            term in full_text for term in ["recently", "lately", "trend", "slowdown"]
        )
        has_time_window = any(
            window in full_text for window in ["days", "month", "quarter", "annual", "202"]
        )
        if has_vague_time and not has_time_window:
            ambiguities.append("vague_time_window")

        return ambiguities

    def _formulate_clarification(self, ambiguity_key: str) -> tuple[str, ClarificationType]:
        if ambiguity_key == "uncontrolled_causality":
            question = (
                "To evaluate AI velocity impacts rigorously, we must control for confounding "
                "factors (such as PR batch size disparity). Should we compare against a "
                "baseline non-AI author cohort in the same repository?"
            )
            return question, ClarificationType.CONSTRAINT

        if ambiguity_key == "vague_time_window":
            question = (
                "Which observation time window should we evaluate? (Recommended: trailing 30 days "
                "or trailing 90 days for statistical sample sufficiency)."
            )
            return question, ClarificationType.GOAL_REFINEMENT

        # Default repository clarification
        question = (
            f"Which target repository should we analyze? (Defaulting to `{self.default_repo}`). "
            "Please confirm or specify an alternate repository."
        )
        return question, ClarificationType.CONSTRAINT

    def _finalize_alignment(self, last_utterance: str, now: datetime) -> tuple[str, bool]:
        self.status = IntentStatus.ALIGNED
        self.aligned_at = now

        # Co-construct formal specification
        self.aligned_specification = (
            f"Aligned analytical investigation for repository '{self.aligned_repo}'. "
            f"Goal: Investigate delivery metrics and flow characteristics grounded in "
            f"canonical telemetry, controlling for confounders and data sufficiency."
        )

        # Derive acceptance criteria strictly from intent
        self.acceptance_criteria = [
            f"Target repository is strictly bounded to '{self.aligned_repo}'.",
            "Evaluate PR flow metrics and dataset quality using pure Python deterministic math.",
            "Enforce 7-tier epistemic claim classification (no unverified causal assertions).",
        ]

        if "ai" in self.raw_prompt.lower() or "copilot" in self.raw_prompt.lower():
            self.acceptance_criteria.append(
                "Isolate AI developer adoption cohorts and evaluate PR size confounders."
            )

        response = (
            f"Intent fully aligned for **{self.aligned_repo}**.\n"
            f"**Specification**: {self.aligned_specification}\n"
            "**Acceptance Criteria**:\n"
            + "\n".join(f"- {c}" for c in self.acceptance_criteria)
            + "\n\nProceeding with deterministic plan execution."
        )

        assistant_turn = IntentTurn(
            speaker=IntentSpeaker.ASSISTANT,
            content=response,
            timestamp=now,
            clarification_type=ClarificationType.ACCEPTANCE_CRITERIA,
        )
        self.dialogue_history.append(assistant_turn)
        return response, True

    def _extract_repository(self, text: str) -> str | None:
        match = re.search(r"\b([a-zA-Z0-9_\-\.]+/[a-zA-Z0-9_\-\.]+)\b", text)
        return match.group(1) if match else None

    def to_canonical_intent(self, ingestion_run_id: str = "run-alignment") -> CanonicalIntent:
        """Convert aligned session state into a persistent CanonicalIntent asset."""
        return CanonicalIntent(
            id=f"intent-{self.session_id}",
            repository=self.aligned_repo,
            author_id=self.context.principal_id,
            title=f"Aligned Investigation: {self.aligned_repo}",
            raw_prompt=self.raw_prompt,
            aligned_specification=self.aligned_specification,
            acceptance_criteria=self.acceptance_criteria,
            synthesized_test_identifiers=[
                "verify_cohort_sample_sufficiency",
                "verify_epistemic_classification_bounds",
            ],
            dialogue_history=list(self.dialogue_history),
            status=self.status,
            epistemic_tier=EpistemicTier.OBSERVED,
            created_at=self.created_at,
            aligned_at=self.aligned_at,
            collected_at=datetime.now(UTC),
            ingestion_run_id=ingestion_run_id,
        )
