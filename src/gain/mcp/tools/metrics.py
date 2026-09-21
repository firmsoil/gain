"""MCP tools for querying deterministic engineering metrics and DORA metrics."""

from __future__ import annotations

from datetime import UTC, datetime

from gain.mcp.auth.context import get_current_principal
from gain.mcp.auth.models import Scope
from gain.mcp.auth.policy import AuthorizationPolicy
from gain.mcp.errors import InvalidInputError, NotFoundError
from gain.mcp.schemas.dora import DORAMetricsResult
from gain.mcp.schemas.metrics import (
    MetricComparison,
    MetricDefinitionResult,
    MetricResult,
)
from gain.mcp.telemetry.logging import trace_mcp_request
from gain.services.dora import DORAService
from gain.services.issue_analytics import IssueAnalyticsService
from gain.services.metrics import MetricService


def get_dora_metrics(
    population: str,
    time_window: str,
    repository: str | None = None,
) -> DORAMetricsResult:
    """Retrieve the current GAIN DORA metrics for a defined population and time window."""
    principal = get_current_principal()
    AuthorizationPolicy.authorize(
        principal=principal,
        required_scope=Scope.METRICS_READ,
        repository=repository,
        operation="get_dora_metrics",
    )

    with trace_mcp_request("tool", "get_dora_metrics", principal.principal_id, principal.tenant_id):
        dora_service = DORAService()
        return dora_service.calculate_dora(
            population=population,
            time_window=time_window,
            repository=repository,
        )


def query_engineering_metrics(
    metric_name: str,
    repository: str | None = None,
    time_window: str | None = None,
) -> MetricResult:
    """Execute an approved set of GAIN engineering metrics (e.g. pr_cycle_time)."""
    principal = get_current_principal()
    AuthorizationPolicy.authorize(
        principal=principal,
        required_scope=Scope.METRICS_READ,
        repository=repository,
        operation="query_engineering_metrics",
    )

    service = MetricService()

    with trace_mcp_request(
        "tool",
        "query_engineering_metrics",
        principal.principal_id,
        principal.tenant_id,
        extra={"metric_name": metric_name, "repository": repository},
    ):
        if metric_name in ("pr_cycle_time", "GAIN-PR-001"):
            res = service.query_pr_cycle_time(repository=repository)
            return MetricResult(
                metric_id=res.metric_id,
                metric_version=res.metric_version,
                metric_name=res.metric_name,
                repository=res.repository,
                time_window=time_window,
                population_count=res.total_evaluated,
                merged_count=res.merged_count,
                summary_stats=res.summary_stats,
                observations_sample=res.observations_sample,
                data_freshness_utc=res.data_freshness_utc,
            )
        elif metric_name in ("monthly_pr_flow_summary", "GAIN-PR-010"):
            stats = service.query_monthly_stats(repository=repository)
            total_created = sum(s.created_count for s in stats)
            total_merged = sum(s.merged_count for s in stats)
            total_closed = sum(s.closed_count for s in stats)
            return MetricResult(
                metric_id="GAIN-PR-010",
                metric_version=1,
                metric_name="monthly_pr_flow_summary",
                repository=repository,
                time_window=time_window,
                population_count=total_created,
                merged_count=total_merged,
                summary_stats={
                    "total_created": total_created,
                    "total_merged": total_merged,
                    "total_closed": total_closed,
                    "months_evaluated": len(stats),
                },
                observations_sample=[s.to_dict() for s in stats[:6]],
                data_freshness_utc=None,
            )
        elif metric_name in ("issue_cycle_time", "GAIN-ISSUE-001"):
            issue_svc = IssueAnalyticsService()
            issue_res = issue_svc.analyze_issues(project_key=repository, repository=repository)
            return MetricResult(
                metric_id="GAIN-ISSUE-001",
                metric_version=1,
                metric_name="issue_cycle_time",
                repository=repository,
                time_window=time_window,
                population_count=issue_res.total_issues,
                merged_count=issue_res.resolved_issues,
                summary_stats=issue_res.cycle_time_stats,
                observations_sample=[
                    {
                        "traceability_rate": issue_res.traceability_rate,
                        "by_type": issue_res.issues_by_type,
                    }
                ],
                data_freshness_utc=datetime.now(UTC).isoformat(),
            )
        else:
            raise InvalidInputError(
                f"Unsupported engineering metric: '{metric_name}'. Supported metrics: "
                "['pr_cycle_time', 'monthly_pr_flow_summary', 'issue_cycle_time']"
            )


def compare_cohorts(
    cohort_a_repo: str,
    cohort_b_repo: str,
    metric_name: str = "pr_cycle_time",
) -> MetricComparison:
    """Compare two explicitly defined populations using approved deterministic metrics."""
    principal = get_current_principal()
    AuthorizationPolicy.authorize(
        principal=principal,
        required_scope=Scope.METRICS_READ,
        repository=cohort_a_repo,
        operation="compare_cohorts",
    )
    AuthorizationPolicy.authorize(
        principal=principal,
        required_scope=Scope.METRICS_READ,
        repository=cohort_b_repo,
        operation="compare_cohorts",
    )

    if metric_name not in ("pr_cycle_time", "GAIN-PR-001"):
        raise InvalidInputError(
            f"Cohort comparison currently supports 'pr_cycle_time', got: '{metric_name}'"
        )

    service = MetricService()
    with trace_mcp_request("tool", "compare_cohorts", principal.principal_id, principal.tenant_id):
        res = service.compare_cohorts(cohort_a_repo=cohort_a_repo, cohort_b_repo=cohort_b_repo)
        return MetricComparison(
            metric_id=res.metric_id,
            metric_version=res.metric_version,
            cohort_a_name=res.cohort_a_name,
            cohort_b_name=res.cohort_b_name,
            cohort_a_count=res.cohort_a_count,
            cohort_b_count=res.cohort_b_count,
            cohort_a_stats=res.cohort_a_stats,
            cohort_b_stats=res.cohort_b_stats,
            delta_p50_seconds=res.delta_p50_seconds,
            delta_mean_seconds=res.delta_mean_seconds,
            comparison_methodology=res.methodology,
        )


def explain_metric(metric_id: str) -> MetricDefinitionResult:
    """Explain the definition and calculation methodology of a named metric from the catalog."""
    principal = get_current_principal()
    AuthorizationPolicy.authorize(
        principal=principal,
        required_scope=Scope.METRICS_READ,
        operation="explain_metric",
    )

    service = MetricService()
    with trace_mcp_request("tool", "explain_metric", principal.principal_id, principal.tenant_id):
        try:
            defn = service.get_metric_definition(metric_id=metric_id)
        except KeyError as err:
            msg = f"Metric definition '{metric_id}' not found in Metric Catalog"
            raise NotFoundError(msg) from err

        return MetricDefinitionResult(
            metric_id=defn["metric_id"],
            metric_version=defn["metric_version"],
            name=defn["name"],
            category=defn["category"],
            type=defn["type"],
            availability=defn["availability"],
            executive=defn.get("executive", False),
            formula=defn["formula"],
            source_fields=defn.get("source_fields", []),
            grain=defn.get("grain", "unknown"),
            unit=defn.get("unit", "units"),
            statistics=defn.get("statistics"),
            filters=defn.get("filters"),
            null_policy=defn.get("null_policy"),
            interpretation=defn.get("interpretation"),
            gaming_risk=defn.get("gaming_risk"),
        )
