"""Unit tests for Runtime.next SLA Slack Budgeting and Tiered Model Routing."""

import pytest

from gain.agent.llm import (
    DeterministicReasoningProvider,
    EdgeSLMReasoningProvider,
    LLMGateway,
    TieredReasoningProvider,
)
from gain.agent.models import Claim, ClaimType, InvestigationPlan
from gain.agent.orchestrator import EngineeringIntelligenceAgent
from gain.agent.runtime.router import ModelTier, TaskCriticality, TieredModelRouter
from gain.agent.runtime.slack import SLABudgetTracker
from gain.config import Settings


def test_sla_budget_tracker_decomposition_and_surplus() -> None:
    tracker = SLABudgetTracker(total_budget_ms=2000.0, sla_target_name="test_pipeline")

    # Allocate for step 1 of 2
    step1_slack = tracker.allocate_step_slack("step-1", steps_remaining=2)
    assert step1_slack > 0.0

    # Simulate fast completion (took 50ms)
    alloc1 = tracker.record_step_completion(
        step_id="step-1",
        allocated_slack_ms=step1_slack,
        actual_duration_ms=50.0,
    )
    assert alloc1.saved_slack_ms == step1_slack - 50.0

    # Allocate for step 2 of 2 (should capture the saved surplus)
    step2_slack = tracker.allocate_step_slack("step-2", steps_remaining=1)
    assert step2_slack > 500.0

    alloc2 = tracker.record_step_completion(
        step_id="step-2",
        allocated_slack_ms=step2_slack,
        actual_duration_ms=100.0,
    )
    assert alloc2.actual_duration_ms == 100.0

    audit = tracker.to_audit_record()
    assert audit["sla_target"] == "test_pipeline"
    assert audit["total_budget_ms"] == 2000.0
    assert audit["step_count"] == 2
    assert audit["total_saved_slack_ms"] > 0.0
    assert not audit["is_exhausted"]


def test_sla_budget_tracker_exhaustion_detection() -> None:
    # Zero budget to test immediate exhaustion
    tracker = SLABudgetTracker(total_budget_ms=0.0)
    assert tracker.is_slack_exhausted is True
    assert tracker.remaining_slack_ms == 0.0


def test_tiered_model_router_decision_matrix() -> None:
    router = TieredModelRouter(
        edge_available=True,
        frontier_available=True,
        min_frontier_slack_ms=1500.0,
    )

    # 1. Critical slack floor (< 500ms) -> Deterministic Cache
    tier, _ = router.select_tier(TaskCriticality.HIGH, remaining_slack_ms=300.0)
    assert tier == ModelTier.DETERMINISTIC_CACHE

    # 2. Low criticality -> Local Edge
    tier, _ = router.select_tier(TaskCriticality.LOW, remaining_slack_ms=5000.0)
    assert tier == ModelTier.LOCAL_EDGE

    # 3. Medium criticality with tight slack (< 1500ms) -> Local Edge
    tier, _ = router.select_tier(TaskCriticality.MEDIUM, remaining_slack_ms=1200.0)
    assert tier == ModelTier.LOCAL_EDGE

    # 4. Medium criticality with ample slack (>= 1500ms) -> Cloud Frontier
    tier, _ = router.select_tier(TaskCriticality.MEDIUM, remaining_slack_ms=3000.0)
    assert tier == ModelTier.CLOUD_FRONTIER

    # 5. High criticality with ample slack -> Cloud Frontier
    tier, _ = router.select_tier(TaskCriticality.HIGH, remaining_slack_ms=4000.0)
    assert tier == ModelTier.CLOUD_FRONTIER

    # 6. High criticality with tight slack -> Local Edge fallback
    tier, _ = router.select_tier(TaskCriticality.HIGH, remaining_slack_ms=1000.0)
    assert tier == ModelTier.LOCAL_EDGE


def test_tiered_model_router_fallback_when_edge_unavailable() -> None:
    router = TieredModelRouter(edge_available=False, frontier_available=True)

    # Low criticality falls back to deterministic cache
    tier, _ = router.select_tier(TaskCriticality.LOW, remaining_slack_ms=2000.0)
    assert tier == ModelTier.DETERMINISTIC_CACHE


@pytest.mark.anyio
async def test_tiered_reasoning_provider_routing() -> None:
    edge_provider = EdgeSLMReasoningProvider(model_name="qwen2.5-coder:7b")
    det_provider = DeterministicReasoningProvider()
    tiered_provider = TieredReasoningProvider(
        edge_provider=edge_provider,
        deterministic_provider=det_provider,
    )
    gateway = LLMGateway(provider=tiered_provider)

    plan = InvestigationPlan(
        plan_id="plan-tier",
        investigation_id="inv-tier",
        intent="Summarize metrics",
        methodology="Tier-Test",
        repository="firmsoil/gain",
    )
    claims = [
        Claim(statement="All tests pass.", classification=ClaimType.OBSERVED),
    ]

    # Test edge routing for low criticality
    briefing_edge = await gateway.generate_briefing(
        intent="Quick check",
        plan=plan,
        claims=claims,
        limitations=[],
        criticality=TaskCriticality.LOW,
        remaining_slack_ms=4000.0,
    )
    assert "Edge SLM Briefing [qwen2.5-coder:7b]" in briefing_edge
    assert gateway.get_audit_metadata()["last_routed_tier"] == "local_edge"

    # Test critical slack fallback to deterministic cache (< 500ms)
    briefing_det = await gateway.generate_briefing(
        intent="Exhausted slack check",
        plan=plan,
        claims=claims,
        limitations=[],
        criticality=TaskCriticality.HIGH,
        remaining_slack_ms=200.0,
    )
    assert "Engineering Intelligence Investigation Briefing" in briefing_det
    assert gateway.get_audit_metadata()["last_routed_tier"] == "deterministic_cache"


@pytest.mark.anyio
async def test_orchestrator_investigation_emits_sla_slack_audit(
    populated_env: Settings,
) -> None:
    agent = EngineeringIntelligenceAgent()
    resp = await agent.investigate(
        query="Investigate pull request cycle time in firmsoil/gain",
        default_repo="firmsoil/gain",
        sla_budget_ms=8000.0,
    )

    assert resp.status == "completed"

    # Verify SLA slack audit event is present in audit trail
    sla_events = [e for e in resp.audit_events if e.get("event") == "sla_slack_audit"]
    assert len(sla_events) == 1

    sla_data = sla_events[0]
    assert sla_data["total_budget_ms"] == 8000.0
    assert sla_data["step_count"] > 0
    assert sla_data["remaining_slack_ms"] > 0.0
    assert "step_allocations" in sla_data
    assert len(sla_data["step_allocations"]) == sla_data["step_count"]
