"""MCP tool for evaluating dataset quality, completeness, and freshness."""

from __future__ import annotations

from gain.mcp.auth.context import get_current_principal
from gain.mcp.auth.models import Scope
from gain.mcp.auth.policy import AuthorizationPolicy
from gain.mcp.schemas.quality import DataQualityResult
from gain.mcp.telemetry.logging import trace_mcp_request
from gain.services.quality import QualityService


def get_data_quality(dataset_id: str = "pull_requests") -> DataQualityResult:
    """Return data quality metrics: freshness, completeness, validity, and known gaps."""
    principal = get_current_principal()
    AuthorizationPolicy.authorize(
        principal=principal,
        required_scope=Scope.QUALITY_READ,
        operation="get_data_quality",
    )

    service = QualityService()
    with trace_mcp_request("tool", "get_data_quality", principal.principal_id, principal.tenant_id):
        eval_res = service.get_dataset_quality(dataset_id=dataset_id)
        return DataQualityResult(
            dataset_id=eval_res.dataset_id,
            total_records=eval_res.total_records,
            valid_records=eval_res.valid_records,
            freshness_utc=eval_res.freshness_utc,
            completeness_score=eval_res.completeness_score,
            validity_score=eval_res.validity_score,
            source_status=eval_res.source_status,
            population_sufficiency=eval_res.population_sufficiency,
            known_gaps=eval_res.known_gaps,
            quality_flags=eval_res.quality_flags,
        )
