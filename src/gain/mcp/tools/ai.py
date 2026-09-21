"""MCP tools for AI impact analysis and economic ROI modeling."""

from __future__ import annotations

from typing import Any

from gain.mcp.auth.context import get_current_principal
from gain.mcp.auth.models import Scope
from gain.mcp.auth.policy import AuthorizationPolicy
from gain.mcp.schemas.ai import AIImpactResult, ROIScenarioResult
from gain.mcp.telemetry.logging import trace_mcp_request
from gain.services.ai_impact import AIImpactService
from gain.services.ai_roi import AIROIService


def analyze_ai_impact(
    cohort_definition: dict[str, Any],
    comparison_cohort: dict[str, Any] | None = None,
) -> AIImpactResult:
    """Expose the GAIN AI impact analytical service with strict attribution taxonomy."""
    principal = get_current_principal()
    repo = cohort_definition.get("repository") if isinstance(cohort_definition, dict) else None
    AuthorizationPolicy.authorize(
        principal=principal,
        required_scope=Scope.METRICS_READ,
        repository=repo,
        operation="analyze_ai_impact",
    )

    with trace_mcp_request(
        "tool", "analyze_ai_impact", principal.principal_id, principal.tenant_id
    ):
        target_repo = str(repo) if repo else "firmsoil/gain"
        service = AIImpactService()
        return service.analyze_impact(
            repository=target_repo,
            cohort_definition=cohort_definition,
            comparison_cohort=comparison_cohort,
        )


def calculate_ai_roi(
    time_period: str,
    population: str,
    investment_cost: float | None = None,
) -> ROIScenarioResult:
    """Expose the GAIN economic-model scenario service for AI developer tooling."""
    principal = get_current_principal()
    AuthorizationPolicy.authorize(
        principal=principal,
        required_scope=Scope.METRICS_READ,
        operation="calculate_ai_roi",
    )

    with trace_mcp_request("tool", "calculate_ai_roi", principal.principal_id, principal.tenant_id):
        service = AIROIService()
        return service.calculate_roi_scenario(
            time_period=time_period,
            population=population,
            investment_cost=investment_cost,
        )
