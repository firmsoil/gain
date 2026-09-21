"""Unit tests for InvestigationPlanner."""

from gain.agent.gateway import AgentGateway
from gain.agent.planner import InvestigationPlanner


def test_planner_creates_cycle_time_plan() -> None:
    gateway = AgentGateway()
    ctx = gateway.create_context()
    planner = InvestigationPlanner()

    plan = planner.create_plan("How has cycle time changed in firmsoil/gain?", ctx)

    assert plan.repository == "firmsoil/gain"
    assert "Cycle-Time" in plan.methodology
    assert len(plan.steps) == 4
    tool_names = [s.tool_name for s in plan.steps]
    assert "query_engineering_metrics" in tool_names
    assert "explain_metric" in tool_names
    assert "get_data_quality" in tool_names
    assert "get_pull_request_details" in tool_names


def test_planner_creates_ai_impact_plan() -> None:
    gateway = AgentGateway()
    ctx = gateway.create_context()
    planner = InvestigationPlanner()

    plan = planner.create_plan("Did Copilot AI improve developer velocity?", ctx)

    assert "AI Delivery Impact" in plan.methodology
    tool_names = [s.tool_name for s in plan.steps]
    assert "analyze_ai_impact" in tool_names
    assert "query_engineering_metrics" in tool_names


def test_planner_creates_dora_plan() -> None:
    gateway = AgentGateway()
    ctx = gateway.create_context()
    planner = InvestigationPlanner()

    plan = planner.create_plan("What are our DORA deployment metrics for org/service-a?", ctx)

    assert plan.repository == "org/service-a"
    assert "DORA" in plan.methodology
    tool_names = [s.tool_name for s in plan.steps]
    assert "get_dora_metrics" in tool_names
