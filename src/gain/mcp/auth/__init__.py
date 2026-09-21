"""Authentication and authorization boundary package for GAIN MCP."""

from __future__ import annotations

from gain.mcp.auth.context import DEV_PRINCIPAL, get_current_principal, set_current_principal
from gain.mcp.auth.models import Principal, Scope
from gain.mcp.auth.policy import AuthorizationPolicy

__all__ = [
    "AuthorizationPolicy",
    "DEV_PRINCIPAL",
    "Principal",
    "Scope",
    "get_current_principal",
    "set_current_principal",
]
