"""Unit tests for AgentGateway."""

import pytest

from gain.agent.gateway import AgentGateway
from gain.mcp.auth.models import Principal, Scope


def test_agent_gateway_creates_valid_context() -> None:
    gateway = AgentGateway(max_steps_per_plan=10)
    principal = Principal(
        principal_id="user-42",
        tenant_id="tenant-acme",
        organization="acme-corp",
        scopes=frozenset({Scope.METRICS_READ.value, Scope.INVESTIGATION_WRITE.value}),
    )

    ctx = gateway.create_context(principal=principal)

    assert ctx.tenant_id == "tenant-acme"
    assert ctx.principal_id == "user-42"
    assert ctx.organization == "acme-corp"
    assert ctx.request_id.startswith("req-")
    assert ctx.investigation_id.startswith("inv-")
    assert "gain:metrics:read" in ctx.scopes


def test_agent_gateway_budget_validation() -> None:
    gateway = AgentGateway(max_steps_per_plan=5)

    gateway.validate_plan_budget(4)  # Within budget

    with pytest.raises(ValueError, match="exceeds maximum allowed budget"):
        gateway.validate_plan_budget(6)
