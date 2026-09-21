"""Integration tests for EngineeringIntelligenceAgent orchestrator."""

import pytest

from gain.agent.github_mcp_client import GitHubMcpClient
from gain.agent.models import ClaimType
from gain.agent.orchestrator import EngineeringIntelligenceAgent
from gain.agent.router import ToolRouter
from gain.config import Settings


@pytest.mark.anyio
async def test_agent_investigate_cycle_time_flow(populated_env: Settings) -> None:
    # Router with mock GitHub client for operational context
    router = ToolRouter(github_client=GitHubMcpClient(mock_mode=True))
    agent = EngineeringIntelligenceAgent(tool_router=router)

    resp = await agent.investigate(
        query="Investigate pull request cycle time in firmsoil/gain",
        default_repo="firmsoil/gain",
    )

    assert resp.status == "completed"
    assert resp.investigation_id.startswith("inv-")
    assert resp.evidence_package_id is not None
    assert len(resp.claims) >= 3

    # Verify claim classifications
    classifications = {c.classification for c in resp.claims}
    assert ClaimType.OBSERVED in classifications
    assert ClaimType.DERIVED in classifications

    # Check briefing text
    assert "Engineering Intelligence Investigation Briefing" in resp.summary
    assert "GAIN-PR-001" in resp.summary or "cycle-time" in resp.summary.lower()


@pytest.mark.anyio
async def test_agent_investigate_ai_impact_handles_missing_telemetry(
    populated_env: Settings,
) -> None:
    agent = EngineeringIntelligenceAgent()

    resp = await agent.investigate(
        query="Did Copilot AI increase our team velocity?",
        default_repo="firmsoil/gain",
    )

    assert resp.status == "completed"
    classifications = {c.classification for c in resp.claims}
    assert ClaimType.UNKNOWN in classifications

    # Verify explicit limitation is surfaced
    assert any("Authoritative AI telemetry" in lim for lim in resp.limitations)
    assert "missing author-level ai telemetry" in resp.summary.lower()


@pytest.mark.anyio
async def test_agent_investigate_degrades_gracefully_when_github_mcp_offline(
    populated_env: Settings,
) -> None:
    # GitHub MCP offline (no endpoint, not mock mode)
    offline_gh = GitHubMcpClient(endpoint_url=None, mock_mode=False)
    router = ToolRouter(github_client=offline_gh)
    agent = EngineeringIntelligenceAgent(tool_router=router)

    resp = await agent.investigate(
        query="What is the cycle time in firmsoil/gain?",
        default_repo="firmsoil/gain",
    )

    assert resp.status == "completed"
    # Live context limitation captured
    assert any(
        "Live GitHub operational context was degraded or unavailable" in lim
        for lim in resp.limitations
    )
    # But analytical metrics still succeeded!
    assert any(c.classification == ClaimType.DERIVED for c in resp.claims)
