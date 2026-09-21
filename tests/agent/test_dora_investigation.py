"""End-to-end investigation tests for DORA and enterprise delivery metrics."""

from __future__ import annotations

import pytest

from gain.agent.models import ClaimType
from gain.agent.orchestrator import EngineeringIntelligenceAgent
from gain.config import Settings
from gain.model.deployment import (
    CanonicalDeployment,
    DeploymentEnvironment,
    DeploymentStatus,
)
from gain.model.issue import SourceSystem
from gain.storage.deployments import write_canonical_deployments


@pytest.mark.anyio
async def test_agent_dora_investigation_with_deployments(
    populated_env: Settings,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    # Add canonical deployments to populated_env canonical dir
    canonical_dir = populated_env.canonical_dir
    from datetime import UTC, datetime

    deps = [
        CanonicalDeployment(
            id="dep-1",
            source_system=SourceSystem.GITHUB,
            repository_name_with_owner="firmsoil/gain",
            environment=DeploymentEnvironment.PRODUCTION,
            status=DeploymentStatus.SUCCESS,
            commit_sha="c1",
            started_at=datetime(2026, 1, 1, 11, 55, 0, tzinfo=UTC),
            completed_at=datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
            collected_at=datetime.now(UTC),
            ingestion_run_id="run-1",
        ),
        CanonicalDeployment(
            id="dep-2",
            source_system=SourceSystem.GITHUB,
            repository_name_with_owner="firmsoil/gain",
            environment=DeploymentEnvironment.PRODUCTION,
            status=DeploymentStatus.FAILURE,
            commit_sha="c2",
            started_at=datetime(2026, 1, 3, 13, 50, 0, tzinfo=UTC),
            completed_at=datetime(2026, 1, 3, 14, 0, 0, tzinfo=UTC),
            collected_at=datetime.now(UTC),
            ingestion_run_id="run-1",
        ),
    ]
    write_canonical_deployments(deps, canonical_dir / "deployments__01.parquet")

    agent = EngineeringIntelligenceAgent()
    response = await agent.investigate(
        query="What is the DORA deployment frequency and change failure rate for firmsoil/gain?",
        default_repo="firmsoil/gain",
    )

    assert response.plan.methodology == "DORA Delivery Flow & Operational Assessment"
    tool_names = [s.tool_name for s in response.plan.steps]
    assert "get_dora_metrics" in tool_names

    # Check extracted claims
    claim_types = [c.classification for c in response.claims]
    assert ClaimType.DERIVED in claim_types

    dora_claim = next((c for c in response.claims if c.metric_id == "GAIN-DORA-003"), None)
    assert dora_claim is not None
    assert "Change failure rate is 50.0%" in dora_claim.statement
