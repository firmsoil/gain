"""Tests for CanonicalDeployment domain model and Parquet persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from gain.model.deployment import (
    CanonicalDeployment,
    DeploymentEnvironment,
    DeploymentStatus,
)
from gain.model.issue import SourceSystem
from gain.storage.deployments import (
    load_deployments_for_repo,
    read_canonical_deployments,
    write_canonical_deployments,
)


def test_canonical_deployment_validation() -> None:
    started = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)
    completed = datetime(2026, 1, 15, 12, 5, 0, tzinfo=UTC)

    dep = CanonicalDeployment(
        id="gh_actions:run-12345",
        source_system=SourceSystem.GITHUB,
        repository_name_with_owner="firmsoil/gain",
        environment=DeploymentEnvironment.PRODUCTION,
        status=DeploymentStatus.SUCCESS,
        commit_sha="a1b2c3d4e5f60000000000000000000000000000",
        ref_name="main",
        deployed_by="octocat",
        started_at=started,
        completed_at=completed,
        collected_at=datetime.now(UTC),
        ingestion_run_id="run-1",
    )

    assert dep.is_production is True
    assert dep.is_success is True
    assert dep.is_failure is False
    assert dep.calculate_duration() == 300.0


def test_canonical_deployment_storage_roundtrip(tmp_path: Path) -> None:
    started = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)
    completed = datetime(2026, 1, 15, 12, 2, 30, tzinfo=UTC)

    dep = CanonicalDeployment(
        id="argocd:dep-67890",
        source_system=SourceSystem.CUSTOM,
        repository_name_with_owner="firmsoil/gain",
        environment=DeploymentEnvironment.STAGING,
        status=DeploymentStatus.FAILURE,
        commit_sha="b2c3d4e5f6a10000000000000000000000000000",
        ref_name="staging",
        deployed_by="argocd-bot",
        started_at=started,
        completed_at=completed,
        collected_at=datetime.now(UTC),
        ingestion_run_id="run-2",
    )

    parquet_file = tmp_path / "deployments__run-2.parquet"
    write_canonical_deployments([dep], parquet_file)

    loaded = read_canonical_deployments(parquet_file)
    assert len(loaded) == 1
    assert loaded[0].id == "argocd:dep-67890"
    assert loaded[0].is_failure is True

    filtered = load_deployments_for_repo("firmsoil/gain", canonical_dir=tmp_path)
    assert len(filtered) == 1
