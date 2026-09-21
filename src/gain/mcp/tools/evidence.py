"""MCP tool for retrieving structured evidence packages."""

from __future__ import annotations

from gain.mcp.auth.context import get_current_principal
from gain.mcp.auth.models import Scope
from gain.mcp.auth.policy import AuthorizationPolicy
from gain.mcp.errors import NotFoundError
from gain.mcp.schemas.evidence import EvidencePackageResult
from gain.mcp.telemetry.logging import trace_mcp_request
from gain.services.evidence import EvidenceService


def get_evidence(evidence_id: str) -> EvidencePackageResult:
    """Retrieve a previously generated evidence package by unique ID."""
    principal = get_current_principal()
    AuthorizationPolicy.authorize(
        principal=principal,
        required_scope=Scope.EVIDENCE_READ,
        operation="get_evidence",
    )

    service = EvidenceService()
    with trace_mcp_request("tool", "get_evidence", principal.principal_id, principal.tenant_id):
        pkg = service.get_evidence(evidence_id=evidence_id)
        if not pkg:
            raise NotFoundError(f"Evidence package '{evidence_id}' not found")

        return EvidencePackageResult(
            evidence_id=pkg.evidence_id,
            claim=pkg.claim,
            claim_classification=pkg.claim_classification,
            metric_id=pkg.metric_id,
            metric_version=pkg.metric_version,
            population_count=pkg.population_count,
            time_window=pkg.time_window,
            data_freshness_utc=pkg.data_freshness_utc,
            statistical_method=pkg.statistical_method,
            assumptions=pkg.assumptions,
            limitations=pkg.limitations,
            confidence_level=pkg.confidence_level,
            source_references=pkg.source_references,
            supporting_artifacts=pkg.supporting_artifacts,
        )
