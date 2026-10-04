"""Unit tests for Teammate.next Intent Alignment and Compiler.next Goal Verification."""

from datetime import UTC, datetime

import pytest

from gain.agent.alignment import AlignmentSession
from gain.agent.models import (
    Claim,
    ClaimType,
    InvestigationPlan,
    PlanStep,
)
from gain.agent.orchestrator import EngineeringIntelligenceAgent
from gain.agent.verifier import IntentVerifier
from gain.config import Settings
from gain.model.intent import CanonicalIntent


def test_alignment_session_multi_turn_clarification() -> None:
    session = AlignmentSession(default_repo="firmsoil/gain", max_turns=3)

    # Turn 1: Ambiguous causal question
    q1, is_aligned1 = session.process_turn("Did AI make our developers faster?")
    assert not is_aligned1
    assert session.status.value == "aligning"
    assert "confounding factors" in q1.lower()
    assert len(session.dialogue_history) == 2  # Human + Assistant

    # Turn 2: Clarify constraints & specify repo
    q2, is_aligned2 = session.process_turn(
        "Yes, compare against non-AI authors in firmsoil/gain over the last 90 days."
    )
    assert is_aligned2
    assert session.status.value == "aligned"
    assert "intent fully aligned" in q2.lower()
    assert session.aligned_repo == "firmsoil/gain"
    assert len(session.acceptance_criteria) >= 3

    # Verify canonical intent export
    canonical = session.to_canonical_intent()
    assert canonical.repository == "firmsoil/gain"
    assert canonical.is_aligned is True
    assert canonical.turn_count == 4
    assert canonical.alignment_duration_seconds() is not None


def test_alignment_session_escape_hatch_max_turns() -> None:
    session = AlignmentSession(default_repo="firmsoil/gain", max_turns=2)

    # Turn 1
    _, aligned1 = session.process_turn("Check performance")
    assert not aligned1

    # Turn 2 (hits max turn limit)
    resp, aligned2 = session.process_turn("Still checking performance")
    assert aligned2
    assert session.status.value == "aligned"
    assert "intent fully aligned" in resp.lower()


def test_intent_verifier_assertion_compilation() -> None:
    verifier = IntentVerifier()

    assertions = verifier.compile_assertions(raw_intent_text="Did Copilot improve velocity?")
    rule_ids = {a.rule_id for a in assertions}

    assert "RULE-PROVENANCE" in rule_ids
    assert "RULE-QUALITY-GATE" in rule_ids
    assert "RULE-CONFOUNDER-ISOLATION" in rule_ids


def test_intent_verifier_plan_validation() -> None:
    verifier = IntentVerifier()
    intent = CanonicalIntent(
        id="intent-test",
        repository="firmsoil/gain",
        author_id="architect",
        title="Cycle Time Audit",
        raw_prompt="Audit cycle time in firmsoil/gain",
        created_at=datetime.now(UTC),
        collected_at=datetime.now(UTC),
        ingestion_run_id="run-1",
    )

    # 1. Invalid plan: wrong repository in step
    bad_plan = InvestigationPlan(
        plan_id="plan-bad",
        investigation_id="inv-1",
        intent="Audit",
        methodology="Test",
        repository="firmsoil/gain",
        steps=[
            PlanStep(
                step_id="step-1",
                description="Query wrong repo",
                tool_name="query_engineering_metrics",
                target_system="gain_mcp",
                arguments={"repository": "other/divergent-repo"},
            ),
        ],
    )
    is_valid, violations = verifier.verify_plan(bad_plan, intent)
    assert not is_valid
    assert any("diverging from aligned repository" in v for v in violations)
    assert any("lacks mandatory 'get_data_quality'" in v for v in violations)

    # 2. Valid plan
    good_plan = InvestigationPlan(
        plan_id="plan-good",
        investigation_id="inv-2",
        intent="Audit",
        methodology="Test",
        repository="firmsoil/gain",
        steps=[
            PlanStep(
                step_id="step-1",
                description="Query metrics",
                tool_name="query_engineering_metrics",
                target_system="gain_mcp",
                arguments={"repository": "firmsoil/gain"},
            ),
            PlanStep(
                step_id="step-2",
                description="Dataset health",
                tool_name="get_data_quality",
                target_system="gain_mcp",
                arguments={"dataset_id": "pull_requests"},
            ),
        ],
    )
    is_good, good_violations = verifier.verify_plan(good_plan, intent)
    assert is_good
    assert len(good_violations) == 0


def test_intent_verifier_claims_epistemic_check() -> None:
    verifier = IntentVerifier()

    claims = [
        Claim(
            claim_id="c-1",
            statement="Copilot directly caused 40% speedup",
            classification=ClaimType.ATTRIBUTED,  # Unwarranted causal attribution
            confidence=0.9,
        ),
        Claim(
            claim_id="c-2",
            statement="PR cycle time is 14400s",
            classification=ClaimType.DERIVED,
            confidence=0.4,  # Low confidence
        ),
    ]

    notes = verifier.verify_claims(claims)
    assert len(notes) == 2
    assert any("downgraded to Associated" in n for n in notes)
    assert any("low confidence" in n for n in notes)


@pytest.mark.anyio
async def test_orchestrator_investigation_with_aligned_intent(
    populated_env: Settings,
) -> None:
    session = AlignmentSession(default_repo="firmsoil/gain")
    session.process_turn("Investigate pull request cycle time in firmsoil/gain")
    session.process_turn("Confirm firmsoil/gain with trailing 30 days window.")
    canonical_intent = session.to_canonical_intent()

    agent = EngineeringIntelligenceAgent()
    resp = await agent.investigate(
        query=canonical_intent.raw_prompt,
        intent=canonical_intent,
    )

    assert resp.status == "completed"
    assert resp.plan.repository == "firmsoil/gain"
    assert resp.evidence_package_id is not None
    assert len(resp.claims) >= 2
