"""Tests for GAIN MCP domain prompts."""

from __future__ import annotations

import pytest
from mcp.server.mcpserver import MCPServer
from mcp.types import GetPromptResult, InputRequiredResult, TextContent


def _extract_prompt_text(res: GetPromptResult | InputRequiredResult) -> str:
    assert isinstance(res, GetPromptResult)
    assert len(res.messages) == 1
    msg = res.messages[0]
    assert isinstance(msg.content, TextContent)
    return msg.content.text


@pytest.mark.anyio
async def test_prompts_listing(mcp_server: MCPServer) -> None:
    prompts = await mcp_server.list_prompts()
    prompt_names = {p.name for p in prompts}
    expected = {
        "dora-executive-brief",
        "dora-investigation",
        "ai-impact-investigation",
        "ai-roi-analysis",
        "metric-change-investigation",
        "repository-engineering-investigation",
        "evidence-review",
        "engineering-health-briefing",
    }
    assert expected.issubset(prompt_names)
    assert len(prompts) == 8


@pytest.mark.anyio
async def test_get_dora_executive_brief_prompt(mcp_server: MCPServer) -> None:
    res = await mcp_server.get_prompt("dora-executive-brief", {"population": "core-team"})
    content = _extract_prompt_text(res)
    assert "core-team" in content
    assert "get_dora_metrics" in content
    assert "query_engineering_metrics" in content


@pytest.mark.anyio
async def test_get_ai_impact_investigation_prompt(mcp_server: MCPServer) -> None:
    res = await mcp_server.get_prompt(
        "ai-impact-investigation",
        {"cohort_a_repo": "firmsoil/gain", "cohort_b_repo": "firmsoil/other"},
    )
    content = _extract_prompt_text(res)
    assert "firmsoil/gain" in content
    assert "analyze_ai_impact" in content
    assert "compare_cohorts" in content


@pytest.mark.anyio
async def test_get_dora_investigation_prompt(mcp_server: MCPServer) -> None:
    res = await mcp_server.get_prompt(
        "dora-investigation",
        {"repository": "firmsoil/gain", "anomaly_description": "Spike in lead time"},
    )
    content = _extract_prompt_text(res)
    assert "firmsoil/gain" in content
    assert "Spike in lead time" in content
    assert "start_investigation" in content


@pytest.mark.anyio
async def test_get_ai_roi_analysis_prompt(mcp_server: MCPServer) -> None:
    res = await mcp_server.get_prompt(
        "ai-roi-analysis",
        {"time_period": "2026-Q1", "population": "backend", "investment_cost": "50000.0"},
    )
    content = _extract_prompt_text(res)
    assert "backend" in content
    assert "calculate_ai_roi" in content
    assert "Modeled" in content


@pytest.mark.anyio
async def test_get_metric_change_investigation_prompt(mcp_server: MCPServer) -> None:
    res = await mcp_server.get_prompt(
        "metric-change-investigation",
        {"metric_id": "GAIN-PR-001", "repository": "firmsoil/gain"},
    )
    content = _extract_prompt_text(res)
    assert "GAIN-PR-001" in content
    assert "firmsoil/gain" in content
    assert "explain_metric" in content


@pytest.mark.anyio
async def test_get_repository_engineering_investigation_prompt(mcp_server: MCPServer) -> None:
    res = await mcp_server.get_prompt(
        "repository-engineering-investigation",
        {"repository": "firmsoil/gain"},
    )
    content = _extract_prompt_text(res)
    assert "firmsoil/gain" in content
    assert "get_data_quality" in content
    assert "get_canonical_entity" in content


@pytest.mark.anyio
async def test_get_evidence_review_prompt(mcp_server: MCPServer) -> None:
    res = await mcp_server.get_prompt(
        "evidence-review",
        {"evidence_id": "ev-001"},
    )
    content = _extract_prompt_text(res)
    assert "ev-001" in content
    assert "get_evidence" in content


@pytest.mark.anyio
async def test_get_engineering_health_briefing_prompt(mcp_server: MCPServer) -> None:
    res = await mcp_server.get_prompt(
        "engineering-health-briefing",
        {"time_window": "last-60-days"},
    )
    content = _extract_prompt_text(res)
    assert "last-60-days" in content
    assert "get_data_quality" in content
