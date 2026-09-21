"""Agent Gateway: authentication, tenant context, correlation IDs, and rate policy."""

from __future__ import annotations

from uuid import uuid4

import structlog

from gain.agent.models import InvestigationContext
from gain.mcp.auth.context import get_current_principal
from gain.mcp.auth.models import Principal

logger = structlog.get_logger(__name__)


class AgentGateway:
    """Gateway for authenticating requests and initializing execution contexts."""

    def __init__(
        self,
        max_steps_per_plan: int = 15,
        default_timeout_seconds: float = 60.0,
    ) -> None:
        self.max_steps_per_plan = max_steps_per_plan
        self.default_timeout_seconds = default_timeout_seconds

    def create_context(
        self,
        principal: Principal | None = None,
        tenant_id: str | None = None,
        organization: str | None = None,
        scopes: list[str] | None = None,
    ) -> InvestigationContext:
        """Create an authenticated, tenant-isolated execution context."""
        active_principal = principal or get_current_principal()

        effective_tenant = tenant_id or active_principal.tenant_id
        effective_org = organization or active_principal.organization
        effective_scopes = scopes or list(active_principal.scopes)

        ctx = InvestigationContext(
            request_id=f"req-{uuid4().hex[:12]}",
            investigation_id=f"inv-{uuid4().hex[:12]}",
            tenant_id=effective_tenant,
            principal_id=active_principal.principal_id,
            organization=effective_org,
            scopes=effective_scopes,
        )

        logger.info(
            "agent_gateway_context_established",
            request_id=ctx.request_id,
            investigation_id=ctx.investigation_id,
            tenant_id=ctx.tenant_id,
            principal_id=ctx.principal_id,
        )
        return ctx

    def validate_plan_budget(self, step_count: int) -> None:
        """Enforce maximum step limits to prevent runaway loops."""
        if step_count > self.max_steps_per_plan:
            raise ValueError(
                f"Plan step count {step_count} exceeds maximum allowed budget "
                f"{self.max_steps_per_plan}"
            )
