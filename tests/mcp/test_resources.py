"""Tests for GAIN MCP addressable resources."""

from __future__ import annotations

import json
from collections.abc import Iterable

import pytest
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import UnexpectedResourceError
from mcp.types import InputRequiredResult

from gain.config import Settings
from gain.mcp.auth.context import set_current_principal
from gain.mcp.auth.models import Principal, Scope
from gain.mcp.errors import AuthorizationError, NotFoundError
from gain.services.evidence import EvidencePackage, EvidenceService
from gain.services.investigation import InvestigationService


def _extract_json(content: object) -> dict[str, object] | list[object]:
    assert isinstance(content, Iterable)
    assert not isinstance(content, InputRequiredResult)
    items = list(content)
    assert len(items) == 1
    item = items[0]
    raw_text = getattr(item, "content", "")  # noqa: B009
    assert isinstance(raw_text, str)
    parsed: dict[str, object] | list[object] = json.loads(raw_text)
    return parsed


@pytest.mark.anyio
async def test_resource_templates_listing(mcp_server: MCPServer) -> None:
    templates = await mcp_server.list_resource_templates()
    uris = {t.uri_template for t in templates}
    expected = {
        "gain://metric-definitions/{metric_id}/{version}",
        "gain://metrics/{metric_id}",
        "gain://cohorts/{cohort_id}",
        "gain://evidence/{evidence_id}",
        "gain://investigations/{investigation_id}",
        "gain://lineage/{target_id}",
        "gain://data-quality/{dataset_id}",
        "gain://contracts/{contract_id}",
    }
    assert expected.issubset(uris)
    assert len(templates) == 8


@pytest.mark.anyio
async def test_read_metric_definition_resource(mcp_server: MCPServer) -> None:
    content = await mcp_server.read_resource("gain://metric-definitions/GAIN-PR-001/1")
    data = _extract_json(content)
    assert isinstance(data, dict)
    assert data["metric_id"] == "GAIN-PR-001"
    assert data["name"] == "pr_cycle_time"


@pytest.mark.anyio
async def test_read_metrics_resource(mcp_server: MCPServer, populated_env: Settings) -> None:
    content = await mcp_server.read_resource("gain://metrics/GAIN-PR-001")
    data = _extract_json(content)
    assert isinstance(data, dict)
    assert data["metric_id"] == "GAIN-PR-001"
    assert "summary_stats" in data


@pytest.mark.anyio
async def test_read_cohort_resource(mcp_server: MCPServer, populated_env: Settings) -> None:
    content = await mcp_server.read_resource("gain://cohorts/firmsoil__gain")
    data = _extract_json(content)
    assert isinstance(data, dict)
    assert data["cohort_id"] == "firmsoil__gain"
    assert data["population_count"] == 3


@pytest.mark.anyio
async def test_read_evidence_resource(mcp_server: MCPServer, populated_env: Settings) -> None:
    service = EvidenceService(populated_env)
    pkg = EvidencePackage(
        evidence_id="ev-res-1",
        claim="Evidence test claim",
        claim_classification="Observed",
        metric_id="GAIN-PR-001",
        metric_version=1,
        population_count=5,
        time_window="2026-Q1",
        data_freshness_utc=None,
        statistical_method="count",
        assumptions=[],
        limitations=[],
        confidence_level="High",
        source_references=[],
        supporting_artifacts=[],
    )
    service.store_evidence(pkg)

    content = await mcp_server.read_resource("gain://evidence/ev-res-1")
    data = _extract_json(content)
    assert isinstance(data, dict)
    assert data["evidence_id"] == "ev-res-1"


@pytest.mark.anyio
async def test_read_investigation_resource(mcp_server: MCPServer, populated_env: Settings) -> None:
    service = InvestigationService(populated_env)
    inv = service.start_investigation(
        title="Resource Test Inv",
        query_specification={},
        tenant_id="default-tenant",
        principal_id="dev-user@gain.local",
    )

    content = await mcp_server.read_resource(f"gain://investigations/{inv.investigation_id}")
    data = _extract_json(content)
    assert isinstance(data, dict)
    assert data["investigation_id"] == inv.investigation_id


@pytest.mark.anyio
async def test_read_lineage_resource(mcp_server: MCPServer, populated_env: Settings) -> None:
    content = await mcp_server.read_resource("gain://lineage/PR_kwDOABC1234")
    data = _extract_json(content)
    assert isinstance(data, dict)
    assert data["target_id"] == "PR_kwDOABC1234"


@pytest.mark.anyio
async def test_read_data_quality_resource(mcp_server: MCPServer, populated_env: Settings) -> None:
    content = await mcp_server.read_resource("gain://data-quality/pull_requests")
    data = _extract_json(content)
    assert isinstance(data, dict)
    assert data["dataset_id"] == "pull_requests"
    assert data["total_records"] == 3


@pytest.mark.anyio
async def test_read_contracts_resource(mcp_server: MCPServer) -> None:
    content = await mcp_server.read_resource("gain://contracts/GAIN-PR-001")
    data = _extract_json(content)
    assert isinstance(data, dict)
    assert data["name"] == "pr_cycle_time"
    assert data["version"] == 1


@pytest.mark.anyio
async def test_read_metrics_resource_monthly_stats(
    mcp_server: MCPServer, populated_env: Settings
) -> None:
    content = await mcp_server.read_resource("gain://metrics/GAIN-PR-010")
    data = _extract_json(content)
    assert isinstance(data, list)
    assert len(data) >= 1


@pytest.mark.anyio
async def test_resource_not_found_errors(mcp_server: MCPServer, populated_env: Settings) -> None:
    for uri in [
        "gain://metric-definitions/UNKNOWN/1",
        "gain://metric-definitions/GAIN-PR-001/invalid-version",
        "gain://metrics/UNKNOWN_METRIC",
        "gain://evidence/nonexistent-ev",
        "gain://investigations/nonexistent-inv",
        "gain://lineage/nonexistent-node",
        "gain://contracts/NON_EXISTENT_CONTRACT",
    ]:
        with pytest.raises(UnexpectedResourceError) as exc_info:
            await mcp_server.read_resource(uri)
        assert isinstance(exc_info.value.__cause__, NotFoundError)


@pytest.mark.anyio
async def test_resource_authorization_denied(
    mcp_server: MCPServer, populated_env: Settings
) -> None:
    # Set principal without EVIDENCE_READ scope
    restricted_principal = Principal(
        principal_id="unauthorized-reader@firmsoil.com",
        tenant_id="tenant-1",
        organization="firmsoil",
        scopes=frozenset({Scope.METRICS_READ}),
    )
    set_current_principal(restricted_principal)

    with pytest.raises(UnexpectedResourceError) as exc_info:
        await mcp_server.read_resource("gain://evidence/any-id")
    assert isinstance(exc_info.value.__cause__, AuthorizationError)
