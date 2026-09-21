"""MCP tool for retrieving canonical entities by authorized identifier."""

from __future__ import annotations

from gain.config import get_settings
from gain.mcp.auth.context import get_current_principal
from gain.mcp.auth.models import Scope
from gain.mcp.auth.policy import AuthorizationPolicy
from gain.mcp.errors import NotFoundError
from gain.mcp.schemas.entity import CanonicalEntityResult
from gain.mcp.telemetry.logging import trace_mcp_request
from gain.model.pr import PullRequest
from gain.storage.analytics import read_canonical


def get_canonical_entity(identifier: str) -> CanonicalEntityResult:
    """Retrieve a canonical GAIN entity (PullRequest) by authorized identifier or node ID."""
    principal = get_current_principal()
    AuthorizationPolicy.authorize(
        principal=principal,
        required_scope=Scope.ENTITY_READ,
        operation="get_canonical_entity",
    )

    settings = get_settings()
    canonical_dir = settings.canonical_dir

    with trace_mcp_request(
        "tool", "get_canonical_entity", principal.principal_id, principal.tenant_id
    ):
        matched_pr: PullRequest | None = None
        if canonical_dir.exists():
            for path in sorted(canonical_dir.glob("*.parquet")):
                try:
                    prs = read_canonical(path)
                    for pr in prs:
                        if pr.github_node_id == identifier or str(pr.number) == identifier:
                            matched_pr = pr
                            break
                except Exception:
                    continue
                if matched_pr:
                    break

        if not matched_pr:
            raise NotFoundError(f"Canonical entity '{identifier}' not found in canonical store")

        # Repository authorization check
        AuthorizationPolicy.authorize(
            principal=principal,
            required_scope=Scope.ENTITY_READ,
            repository=matched_pr.repository_name_with_owner,
            operation="get_canonical_entity",
        )

        return CanonicalEntityResult(
            entity_type="PullRequest",
            identifier=matched_pr.github_node_id,
            repository=matched_pr.repository_name_with_owner,
            number=matched_pr.number,
            state=matched_pr.state,
            is_draft=matched_pr.is_draft,
            author_login=matched_pr.author_login,
            created_at_utc=matched_pr.created_at.isoformat(),
            closed_at_utc=matched_pr.closed_at.isoformat() if matched_pr.closed_at else None,
            merged_at_utc=matched_pr.merged_at.isoformat() if matched_pr.merged_at else None,
            cycle_time_seconds=matched_pr.cycle_time_seconds(),
            additions=matched_pr.additions,
            deletions=matched_pr.deletions,
            changed_files=matched_pr.changed_files,
            provenance={
                "ingestion_run_id": matched_pr.ingestion_run_id,
                "collected_at": matched_pr.collected_at.isoformat(),
            },
        )
