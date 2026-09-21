"""Authentication and authorization data models for GAIN MCP."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Scope(StrEnum):
    METRICS_READ = "gain:metrics:read"
    EVIDENCE_READ = "gain:evidence:read"
    QUALITY_READ = "gain:quality:read"
    ENTITY_READ = "gain:entity:read"
    INVESTIGATION_READ = "gain:investigation:read"
    INVESTIGATION_WRITE = "gain:investigation:write"
    ADMIN = "gain:admin"


@dataclass(frozen=True)
class Principal:
    principal_id: str
    tenant_id: str
    organization: str
    scopes: frozenset[str] = field(default_factory=frozenset)
    allowed_repositories: frozenset[str] = field(default_factory=frozenset)
    auth_mode: str = "dev"  # "dev", "test", "production"

    def has_scope(self, scope: Scope | str) -> bool:
        scope_str = str(scope)
        return Scope.ADMIN in self.scopes or scope_str in self.scopes

    def is_repository_allowed(self, repo: str | None) -> bool:
        if repo is None:
            return True
        if "*" in self.allowed_repositories:
            return True
        return repo in self.allowed_repositories
