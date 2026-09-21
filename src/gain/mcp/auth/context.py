"""Context variable storage for the current authenticated principal."""

from __future__ import annotations

from contextvars import ContextVar

from gain.mcp.auth.models import Principal, Scope

# Default development principal for local stdio/testing
DEV_PRINCIPAL = Principal(
    principal_id="dev-user@gain.local",
    tenant_id="default-tenant",
    organization="firmsoil",
    scopes=frozenset(
        {
            Scope.METRICS_READ,
            Scope.EVIDENCE_READ,
            Scope.QUALITY_READ,
            Scope.ENTITY_READ,
            Scope.INVESTIGATION_READ,
            Scope.INVESTIGATION_WRITE,
        }
    ),
    allowed_repositories=frozenset({"*"}),
    auth_mode="dev",
)

_current_principal: ContextVar[Principal] = ContextVar("current_principal", default=DEV_PRINCIPAL)


def get_current_principal() -> Principal:
    return _current_principal.get()


def set_current_principal(principal: Principal) -> None:
    _current_principal.set(principal)
