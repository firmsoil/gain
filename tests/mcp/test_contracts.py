"""Contract tests ensuring public MCP interfaces remain immutable and backward compatible."""

from __future__ import annotations

import pytest
from mcp.server.mcpserver import MCPServer

from gain.mcp.schemas.ai import AIImpactResult, ROIScenarioResult
from gain.mcp.schemas.dora import DORAMetricsResult
from gain.mcp.schemas.entity import CanonicalEntityResult
from gain.mcp.schemas.evidence import EvidencePackageResult
from gain.mcp.schemas.investigation import InvestigationStatus
from gain.mcp.schemas.metrics import (
    MetricResult,
)

CANONICAL_TOOL_CATALOG = [
    "get_dora_metrics",
    "query_engineering_metrics",
    "compare_cohorts",
    "analyze_ai_impact",
    "calculate_ai_roi",
    "explain_metric",
    "get_metric_lineage",
    "get_evidence",
    "start_investigation",
    "get_investigation",
    "get_data_quality",
    "get_canonical_entity",
]

CANONICAL_RESOURCE_TEMPLATES = [
    "gain://metric-definitions/{metric_id}/{version}",
    "gain://metrics/{metric_id}",
    "gain://cohorts/{cohort_id}",
    "gain://evidence/{evidence_id}",
    "gain://investigations/{investigation_id}",
    "gain://lineage/{target_id}",
    "gain://data-quality/{dataset_id}",
    "gain://contracts/{contract_id}",
]

CANONICAL_PROMPTS = [
    "dora-executive-brief",
    "dora-investigation",
    "ai-impact-investigation",
    "ai-roi-analysis",
    "metric-change-investigation",
    "repository-engineering-investigation",
    "evidence-review",
    "engineering-health-briefing",
]


@pytest.mark.anyio
async def test_tool_catalog_immutability(mcp_server: MCPServer) -> None:
    tools = await mcp_server.list_tools()
    registered_names = [t.name for t in tools]
    for expected_name in CANONICAL_TOOL_CATALOG:
        assert expected_name in registered_names, (
            f"Contract violation: tool '{expected_name}' missing"
        )


@pytest.mark.anyio
async def test_resource_templates_immutability(mcp_server: MCPServer) -> None:
    templates = await mcp_server.list_resource_templates()
    registered_templates = [t.uri_template for t in templates]
    for expected_uri in CANONICAL_RESOURCE_TEMPLATES:
        assert expected_uri in registered_templates, (
            f"Contract violation: URI template '{expected_uri}' missing"
        )


@pytest.mark.anyio
async def test_prompts_immutability(mcp_server: MCPServer) -> None:
    prompts = await mcp_server.list_prompts()
    registered_prompts = [p.name for p in prompts]
    for expected_prompt in CANONICAL_PROMPTS:
        assert expected_prompt in registered_prompts, (
            f"Contract violation: prompt '{expected_prompt}' missing"
        )


def test_schema_field_contracts() -> None:
    # Validate required fields on public schemas
    metric_fields = MetricResult.model_fields.keys()
    assert {
        "metric_id",
        "metric_version",
        "metric_name",
        "population_count",
        "summary_stats",
    }.issubset(metric_fields)

    dora_fields = DORAMetricsResult.model_fields.keys()
    assert {
        "status",
        "population",
        "time_window",
        "change_lead_time",
        "deployment_frequency",
        "failed_deployment_recovery_time",
        "change_fail_rate",
        "deployment_rework_rate",
    }.issubset(dora_fields)

    ai_fields = AIImpactResult.model_fields.keys()
    assert {
        "status",
        "classification",
        "cohort_definition",
        "confidence_level",
        "limitations",
    }.issubset(ai_fields)

    roi_fields = ROIScenarioResult.model_fields.keys()
    assert {
        "status",
        "is_modeled",
        "time_period",
        "population",
        "assumptions",
        "limitations",
    }.issubset(roi_fields)

    entity_fields = CanonicalEntityResult.model_fields.keys()
    assert {"entity_type", "identifier", "repository", "number", "state"}.issubset(entity_fields)

    evidence_fields = EvidencePackageResult.model_fields.keys()
    assert {"evidence_id", "claim", "claim_classification", "metric_id", "metric_version"}.issubset(
        evidence_fields
    )

    inv_fields = InvestigationStatus.model_fields.keys()
    assert {"investigation_id", "plan_id", "tenant_id", "title", "status"}.issubset(inv_fields)
