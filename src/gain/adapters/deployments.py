"""Enterprise source adapter normalizing CI/CD and deployment telemetry into CanonicalDeployment."""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from gain.adapters.base import BaseSourceAdapter
from gain.config import Settings
from gain.model.deployment import (
    CanonicalDeployment,
    DeploymentEnvironment,
    DeploymentStatus,
)
from gain.model.issue import SourceSystem
from gain.storage.deployments import write_canonical_deployments


class DeploymentSourceAdapter(BaseSourceAdapter[CanonicalDeployment]):
    """Adapter for CI/CD systems, GitHub Actions, and ArgoCD deployment events."""

    def __init__(
        self,
        source_system: SourceSystem = SourceSystem.GITHUB,
        settings: Settings | None = None,
    ) -> None:
        super().__init__(settings=settings)
        self._source_system = source_system

    @property
    def source_system(self) -> SourceSystem:
        return self._source_system

    @property
    def entity_type(self) -> str:
        return "deployments"

    def persist_canonical(self, records: list[CanonicalDeployment], path: Path) -> None:
        write_canonical_deployments(records, path)

    def normalize_record(
        self,
        raw_record: dict[str, Any],
        run_id: str,
        collected_at: datetime,
    ) -> CanonicalDeployment:
        """Normalize deployment JSON dictionary into CanonicalDeployment."""
        dep_id = str(
            raw_record.get("id") or raw_record.get("deployment_id") or raw_record.get("run_id")
        )
        repo = str(raw_record.get("repository") or raw_record.get("repo") or "unknown/repo")
        commit_sha = str(
            raw_record.get("commit_sha")
            or raw_record.get("head_sha")
            or raw_record.get("sha")
            or "0000000000000000000000000000000000000000"
        )
        ref_name = raw_record.get("ref_name") or raw_record.get("ref") or raw_record.get("branch")
        deployed_by = (
            raw_record.get("deployed_by")
            or (raw_record.get("actor") or {}).get("login")
            or raw_record.get("trigger_actor")
        )

        # Environment mapping
        env_raw = str(raw_record.get("environment") or "production").lower()
        environment = self._map_environment(env_raw)

        # Status mapping
        status_raw = str(
            raw_record.get("status")
            or raw_record.get("conclusion")
            or raw_record.get("state")
            or "success"
        ).lower()
        status = self._map_status(status_raw)

        # Timestamps & Duration
        started_raw = (
            raw_record.get("started_at") or raw_record.get("created_at") or collected_at.isoformat()
        )
        started_at = self._parse_iso(str(started_raw))
        completed_at = (
            self._parse_iso(str(raw_record["completed_at"]))
            if raw_record.get("completed_at")
            else None
        )

        duration = None
        if "duration_seconds" in raw_record and raw_record["duration_seconds"] is not None:
            with contextlib.suppress(ValueError, TypeError):
                duration = float(raw_record["duration_seconds"])
        elif completed_at is not None:
            duration = max(0.0, (completed_at - started_at).total_seconds())

        return CanonicalDeployment(
            id=f"{self.source_system.value}:{dep_id}",
            source_system=self.source_system,
            repository_name_with_owner=repo,
            environment=environment,
            status=status,
            commit_sha=commit_sha,
            ref_name=str(ref_name) if ref_name else None,
            deployed_by=str(deployed_by) if deployed_by else None,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration,
            collected_at=collected_at,
            ingestion_run_id=run_id,
        )

    @staticmethod
    def _map_environment(env_raw: str) -> DeploymentEnvironment:
        if "prod" in env_raw:
            return DeploymentEnvironment.PRODUCTION
        if "stag" in env_raw or "qa" in env_raw:
            return DeploymentEnvironment.STAGING
        if "canary" in env_raw:
            return DeploymentEnvironment.CANARY
        return DeploymentEnvironment.DEVELOPMENT

    @staticmethod
    def _map_status(status_raw: str) -> DeploymentStatus:
        if status_raw in {"success", "succeeded", "healthy", "passed"}:
            return DeploymentStatus.SUCCESS
        if status_raw in {"failure", "failed", "error", "degraded"}:
            return DeploymentStatus.FAILURE
        if status_raw in {"cancelled", "canceled", "skipped", "aborted"}:
            return DeploymentStatus.CANCELLED
        return DeploymentStatus.IN_PROGRESS

    @staticmethod
    def _parse_iso(value: str) -> datetime:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
