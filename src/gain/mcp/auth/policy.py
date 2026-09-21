"""Authorization policy engine enforcing tenant boundaries and scope checks."""

from __future__ import annotations

from gain.mcp.auth.models import Principal, Scope
from gain.mcp.errors import AuthorizationError


class AuthorizationPolicy:
    """Enforces fine-grained authorization before accessing GAIN data."""

    @classmethod
    def authorize(
        cls,
        principal: Principal,
        required_scope: Scope | str,
        repository: str | None = None,
        tenant_id: str | None = None,
        operation: str = "operation",
    ) -> None:
        # 1. Tenant Check
        if tenant_id and tenant_id != principal.tenant_id:
            raise AuthorizationError(
                f"Tenant mismatch: principal belongs to tenant '{principal.tenant_id}', "
                f"requested tenant '{tenant_id}'",
                details={
                    "principal_id": principal.principal_id,
                    "principal_tenant": principal.tenant_id,
                    "requested_tenant": tenant_id,
                    "operation": operation,
                },
            )

        # 2. Scope Check
        if not principal.has_scope(required_scope):
            raise AuthorizationError(
                f"Principal '{principal.principal_id}' lacks required scope '{required_scope}' "
                f"for {operation}",
                details={
                    "principal_id": principal.principal_id,
                    "required_scope": str(required_scope),
                    "held_scopes": sorted(principal.scopes),
                    "operation": operation,
                },
            )

        # 3. Repository Scope Check
        if repository and not principal.is_repository_allowed(repository):
            raise AuthorizationError(
                f"Principal '{principal.principal_id}' is not authorized to access "
                f"repository '{repository}'",
                details={
                    "principal_id": principal.principal_id,
                    "requested_repository": repository,
                    "allowed_repositories": sorted(principal.allowed_repositories),
                    "operation": operation,
                },
            )
