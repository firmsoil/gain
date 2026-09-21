"""MCP tools for managing durable, application-owned investigations."""

from __future__ import annotations

from typing import Any

from gain.mcp.auth.context import get_current_principal
from gain.mcp.auth.models import Scope
from gain.mcp.auth.policy import AuthorizationPolicy
from gain.mcp.errors import NotFoundError
from gain.mcp.schemas.investigation import InvestigationStatus, InvestigationSummary
from gain.mcp.telemetry.logging import trace_mcp_request
from gain.services.investigation import InvestigationService


def start_investigation(
    title: str,
    query_specification: dict[str, Any],
) -> InvestigationSummary:
    """Create durable GAIN investigation state for an authorized investigation."""
    principal = get_current_principal()
    AuthorizationPolicy.authorize(
        principal=principal,
        required_scope=Scope.INVESTIGATION_WRITE,
        operation="start_investigation",
    )

    service = InvestigationService()
    with trace_mcp_request(
        "tool", "start_investigation", principal.principal_id, principal.tenant_id
    ):
        record = service.start_investigation(
            title=title,
            query_specification=query_specification,
            tenant_id=principal.tenant_id,
            principal_id=principal.principal_id,
        )

        return InvestigationSummary(
            investigation_id=record.investigation_id,
            plan_id=record.plan_id,
            title=record.title,
            status=record.status,
            analysis_version=record.analysis_version,
            created_at_utc=record.created_at_utc,
            updated_at_utc=record.updated_at_utc,
            evidence_references=record.evidence_references,
            result_references=record.result_references,
        )


def get_investigation(investigation_id: str) -> InvestigationStatus:
    """Retrieve persisted investigation status/result within the authorized caller's tenant."""
    principal = get_current_principal()
    AuthorizationPolicy.authorize(
        principal=principal,
        required_scope=Scope.INVESTIGATION_READ,
        operation="get_investigation",
    )

    service = InvestigationService()
    with trace_mcp_request(
        "tool", "get_investigation", principal.principal_id, principal.tenant_id
    ):
        record = service.get_investigation(
            investigation_id=investigation_id,
            tenant_id=principal.tenant_id,
        )
        if not record:
            # Tenant isolation: return NotFoundError whether it doesn't exist or belongs to another
            raise NotFoundError(f"Investigation '{investigation_id}' not found")

        return InvestigationStatus(
            investigation_id=record.investigation_id,
            plan_id=record.plan_id,
            tenant_id=record.tenant_id,
            principal_id=record.principal_id,
            title=record.title,
            status=record.status,
            analysis_version=record.analysis_version,
            query_specification=record.query_specification,
            created_at_utc=record.created_at_utc,
            updated_at_utc=record.updated_at_utc,
            evidence_references=record.evidence_references,
            result_references=record.result_references,
        )
