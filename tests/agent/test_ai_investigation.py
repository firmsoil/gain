"""Integration tests for Agent AI impact and economic ROI investigations."""

import pytest

from gain.agent.models import ClaimType
from gain.agent.orchestrator import EngineeringIntelligenceAgent
from gain.config import Settings


@pytest.mark.anyio
async def test_agent_investigate_ai_roi_workflow(populated_env: Settings) -> None:
    agent = EngineeringIntelligenceAgent()

    resp = await agent.investigate(
        query="What is our projected AI developer ROI and savings in firmsoil/gain?",
        default_repo="firmsoil/gain",
    )

    assert resp.status == "completed"
    assert resp.investigation_id.startswith("inv-")
    assert resp.evidence_package_id is not None

    classifications = {c.classification for c in resp.claims}
    # ROI inquiry generates MODELED economic claims and ASSUMED parameters
    assert ClaimType.MODELED in classifications
    assert ClaimType.ASSUMED in classifications

    # Check briefing text contains modeled ROI statements
    assert "Modeled expected AI developer ROI is projected" in resp.summary
    assert "Assumed parameter:" in resp.summary
