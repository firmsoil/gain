"""MCP tool for source-to-result lineage traversal."""

from __future__ import annotations

from gain.mcp.auth.context import get_current_principal
from gain.mcp.auth.models import Scope
from gain.mcp.auth.policy import AuthorizationPolicy
from gain.mcp.errors import NotFoundError
from gain.mcp.schemas.lineage import LineageResult, LineageStep
from gain.mcp.telemetry.logging import trace_mcp_request
from gain.services.lineage import LineageService


def get_metric_lineage(github_node_id: str) -> LineageResult:
    """Return end-to-end source-to-result lineage for a pull request or metric observation."""
    principal = get_current_principal()
    AuthorizationPolicy.authorize(
        principal=principal,
        required_scope=Scope.METRICS_READ,
        operation="get_metric_lineage",
    )

    service = LineageService()
    with trace_mcp_request(
        "tool", "get_metric_lineage", principal.principal_id, principal.tenant_id
    ):
        trace = service.get_pr_lineage(github_node_id=github_node_id)
        if not trace:
            raise NotFoundError(f"Lineage trace not found for identifier: '{github_node_id}'")

        steps = [
            LineageStep(layer=n.layer, identifier=n.identifier, metadata=n.metadata)
            for n in trace.nodes
        ]
        return LineageResult(
            target_id=trace.target_id,
            target_type=trace.target_type,
            provenance_chain=trace.provenance_chain,
            steps=steps,
        )
