"""Tests for GAIN MCP authorization, tenant isolation, and security scopes."""

from __future__ import annotations

import pytest

from gain.config import Settings
from gain.mcp.auth.context import set_current_principal
from gain.mcp.auth.models import Principal, Scope
from gain.mcp.errors import AuthorizationError, NotFoundError
from gain.mcp.tools import (
    get_investigation,
    query_engineering_metrics,
    start_investigation,
)


def test_missing_scope_raises_authorization_error() -> None:
    restricted_principal = Principal(
        principal_id="restricted-user@firmsoil.com",
        tenant_id="tenant-1",
        organization="firmsoil",
        scopes=frozenset({Scope.QUALITY_READ}),  # Only quality read, no metrics read
        allowed_repositories=frozenset({"*"}),
    )
    set_current_principal(restricted_principal)

    with pytest.raises(AuthorizationError) as exc_info:
        query_engineering_metrics(metric_name="pr_cycle_time")

    assert "lacks required scope" in str(exc_info.value)
    assert exc_info.value.code == "AUTHORIZATION_FAILURE"


def test_repository_domain_restriction(populated_env: Settings) -> None:
    restricted_principal = Principal(
        principal_id="repo-restricted-user@firmsoil.com",
        tenant_id="tenant-1",
        organization="firmsoil",
        scopes=frozenset({Scope.METRICS_READ, Scope.ENTITY_READ}),
        allowed_repositories=frozenset({"firmsoil/other-repo"}),  # 'firmsoil/gain' not permitted
    )
    set_current_principal(restricted_principal)

    with pytest.raises(AuthorizationError) as exc_info:
        query_engineering_metrics(metric_name="pr_cycle_time", repository="firmsoil/gain")

    assert "is not authorized to access repository 'firmsoil/gain'" in str(exc_info.value)


def test_tenant_isolation_on_investigation(populated_env: Settings) -> None:
    tenant_a_principal = Principal(
        principal_id="user-a@tenant-a.com",
        tenant_id="tenant-a",
        organization="org-a",
        scopes=frozenset({Scope.INVESTIGATION_WRITE, Scope.INVESTIGATION_READ}),
    )
    set_current_principal(tenant_a_principal)

    inv = start_investigation(
        title="Tenant A Investigation",
        query_specification={"metric": "pr_cycle_time"},
    )
    assert inv.investigation_id is not None

    # Tenant A can read it
    status_a = get_investigation(inv.investigation_id)
    assert status_a.investigation_id == inv.investigation_id

    # Switch to Tenant B principal
    tenant_b_principal = Principal(
        principal_id="user-b@tenant-b.com",
        tenant_id="tenant-b",
        organization="org-b",
        scopes=frozenset({Scope.INVESTIGATION_WRITE, Scope.INVESTIGATION_READ}),
    )
    set_current_principal(tenant_b_principal)

    # Tenant B querying Tenant A's investigation must raise NotFoundError
    # (no tenant leakage or enumeration)
    with pytest.raises(NotFoundError):
        get_investigation(inv.investigation_id)
