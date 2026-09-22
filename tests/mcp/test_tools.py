"""Tests for all 12 GAIN MCP domain tools."""

from __future__ import annotations

import pytest
from mcp.server.mcpserver import MCPServer

from gain.config import Settings
from gain.mcp.errors import InvalidInputError, NotFoundError
from gain.mcp.schemas.ai import AIImpactResult, ClaimClassification, ROIScenarioResult
from gain.mcp.schemas.dora import DORAMetricsResult
from gain.mcp.schemas.entity import CanonicalEntityResult
from gain.mcp.schemas.evidence import EvidencePackageResult
from gain.mcp.schemas.investigation import InvestigationStatus, InvestigationSummary
from gain.mcp.schemas.lineage import LineageResult
from gain.mcp.schemas.metrics import (
    MetricComparison,
    MetricDefinitionResult,
    MetricResult,
)
from gain.mcp.schemas.quality import DataQualityResult
from gain.mcp.tools import (
    analyze_ai_impact,
    calculate_ai_roi,
    compare_cohorts,
    explain_metric,
    get_canonical_entity,
    get_data_quality,
    get_dora_metrics,
    get_evidence,
    get_investigation,
    get_metric_lineage,
    query_engineering_metrics,
    start_investigation,
)
from gain.services.evidence import EvidencePackage, EvidenceService


@pytest.mark.anyio
async def test_server_tools_listing(mcp_server: MCPServer) -> None:
    tools = await mcp_server.list_tools()
    tool_names = {t.name for t in tools}
    expected = {
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
    }
    assert expected.issubset(tool_names)
    assert len(tools) == 12


def test_get_dora_metrics_returns_insufficient_data() -> None:
    res = get_dora_metrics(population="all", time_window="last-90-days")
    assert isinstance(res, DORAMetricsResult)
    assert res.status == "insufficient_data"
    assert res.change_lead_time.status == "insufficient_data"
    assert "GitHub Deployments API" in res.missing_dependencies[0]


def test_query_engineering_metrics_pr_cycle_time(populated_env: Settings) -> None:
    res = query_engineering_metrics(metric_name="pr_cycle_time")
    assert isinstance(res, MetricResult)
    assert res.metric_id == "GAIN-PR-001"
    assert res.population_count == 3
    assert res.merged_count == 2
    assert res.summary_stats["count"] == 2
    assert len(res.observations_sample) == 2

    # Verify MCP requests metric was incremented
    from gain.telemetry.metrics import MCP_REQUESTS_TOTAL

    assert MCP_REQUESTS_TOTAL.get(tool_name="query_engineering_metrics", status="success") >= 1.0


def test_query_engineering_metrics_monthly_stats(populated_env: Settings) -> None:
    res = query_engineering_metrics(metric_name="monthly_pr_flow_summary")
    assert isinstance(res, MetricResult)
    assert res.metric_id == "GAIN-PR-010"
    assert res.merged_count == 2
    assert "total_created" in res.summary_stats


def test_query_engineering_metrics_unsupported() -> None:
    with pytest.raises(InvalidInputError):
        query_engineering_metrics(metric_name="unsupported_metric_xyz")


def test_compare_cohorts(populated_env: Settings) -> None:
    res = compare_cohorts(cohort_a_repo="firmsoil/gain", cohort_b_repo="firmsoil/gain")
    assert isinstance(res, MetricComparison)
    assert res.metric_id == "GAIN-PR-001"
    assert res.cohort_a_name == "firmsoil/gain"
    assert res.cohort_b_name == "firmsoil/gain"
    assert res.cohort_a_count == 3
    assert res.cohort_b_count == 3


def test_analyze_ai_impact_returns_insufficient_data() -> None:
    res = analyze_ai_impact(cohort_definition={"team": "backend"})
    assert isinstance(res, AIImpactResult)
    assert res.status == "insufficient_data"
    assert res.classification == ClaimClassification.UNKNOWN
    assert len(res.limitations) > 0


def test_calculate_ai_roi() -> None:
    res = calculate_ai_roi(time_period="2026-Q1", population="engineers", investment_cost=10000.0)
    assert isinstance(res, ROIScenarioResult)
    assert res.status == "available"
    assert res.is_modeled is True
    assert res.roi_percentage is not None
    assert res.net_benefit is not None


def test_explain_metric() -> None:
    res = explain_metric("GAIN-PR-001")
    assert isinstance(res, MetricDefinitionResult)
    assert res.metric_id == "GAIN-PR-001"
    assert res.name == "pr_cycle_time"
    assert "merged_at - created_at" in res.formula


def test_explain_metric_not_found() -> None:
    with pytest.raises(NotFoundError):
        explain_metric("UNKNOWN-METRIC-999")


def test_get_metric_lineage(populated_env: Settings) -> None:
    res = get_metric_lineage(github_node_id="PR_kwDOABC1234")
    assert isinstance(res, LineageResult)
    assert res.target_id == "PR_kwDOABC1234"
    assert len(res.steps) >= 2


def test_get_metric_lineage_not_found(populated_env: Settings) -> None:
    with pytest.raises(NotFoundError):
        get_metric_lineage(github_node_id="NON_EXISTENT_NODE")


def test_evidence_workflow(populated_env: Settings) -> None:
    service = EvidenceService(populated_env)
    pkg = EvidencePackage(
        evidence_id="ev-001",
        claim="PR cycle time decreased in Q1",
        claim_classification="Derived",
        metric_id="GAIN-PR-001",
        metric_version=1,
        population_count=10,
        time_window="2026-Q1",
        data_freshness_utc="2026-01-05T00:00:00Z",
        statistical_method="p50 median comparison",
        assumptions=["Standard working hours"],
        limitations=["Small sample size"],
        confidence_level="Medium",
        source_references=["run-test-001"],
        supporting_artifacts=["data/canonical/prs.parquet"],
    )
    service.store_evidence(pkg)

    res = get_evidence(evidence_id="ev-001")
    assert isinstance(res, EvidencePackageResult)
    assert res.evidence_id == "ev-001"
    assert res.claim == pkg.claim


def test_evidence_not_found(populated_env: Settings) -> None:
    with pytest.raises(NotFoundError):
        get_evidence("ev-non-existent")


def test_investigation_lifecycle(populated_env: Settings) -> None:
    summary = start_investigation(
        title="Test Investigation",
        query_specification={"metric": "pr_cycle_time", "repo": "firmsoil/gain"},
    )
    assert isinstance(summary, InvestigationSummary)
    assert summary.status == "INITIATED"

    status = get_investigation(summary.investigation_id)
    assert isinstance(status, InvestigationStatus)
    assert status.investigation_id == summary.investigation_id
    assert status.title == "Test Investigation"


def test_get_data_quality(populated_env: Settings) -> None:
    res = get_data_quality("pull_requests")
    assert isinstance(res, DataQualityResult)
    assert res.total_records == 3
    assert res.valid_records == 3
    assert res.validity_score == 1.0
    assert res.source_status == "HEALTHY"


def test_get_canonical_entity(populated_env: Settings) -> None:
    res = get_canonical_entity("PR_kwDOABC1234")
    assert isinstance(res, CanonicalEntityResult)
    assert res.identifier == "PR_kwDOABC1234"
    assert res.number == 101
    assert res.repository == "firmsoil/gain"
    assert res.cycle_time_seconds == 14400.0


def test_get_canonical_entity_not_found(populated_env: Settings) -> None:
    with pytest.raises(NotFoundError):
        get_canonical_entity("PR_DOES_NOT_EXIST")


def test_compare_cohorts_unsupported_metric(populated_env: Settings) -> None:
    with pytest.raises(InvalidInputError) as exc_info:
        compare_cohorts(
            cohort_a_repo="firmsoil/gain",
            cohort_b_repo="firmsoil/gain",
            metric_name="unsupported_metric",
        )
    assert "Cohort comparison currently supports 'pr_cycle_time'" in str(exc_info.value)


def test_get_canonical_entity_by_number(populated_env: Settings) -> None:
    res = get_canonical_entity("101")
    assert isinstance(res, CanonicalEntityResult)
    assert res.identifier == "PR_kwDOABC1234"
    assert res.number == 101


def test_get_canonical_entity_unauthorized_repo(populated_env: Settings) -> None:
    from gain.mcp.auth.context import set_current_principal
    from gain.mcp.auth.models import Principal, Scope
    from gain.mcp.errors import AuthorizationError

    restricted_principal = Principal(
        principal_id="restricted@firmsoil.com",
        tenant_id="tenant-1",
        organization="firmsoil",
        scopes=frozenset({Scope.ENTITY_READ}),
        allowed_repositories=frozenset({"firmsoil/other-repo"}),
    )
    set_current_principal(restricted_principal)

    with pytest.raises(AuthorizationError) as exc_info:
        get_canonical_entity("PR_kwDOABC1234")
    assert "not authorized to access repository 'firmsoil/gain'" in str(exc_info.value)
