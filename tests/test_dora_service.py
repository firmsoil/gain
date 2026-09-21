"""Tests for deterministic DORAService."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from gain.config import Settings
from gain.model.commit import CanonicalCommit
from gain.model.deployment import (
    CanonicalDeployment,
    DeploymentEnvironment,
    DeploymentStatus,
)
from gain.model.issue import SourceSystem
from gain.services.dora import DORAService
from gain.storage.commits import write_canonical_commits
from gain.storage.deployments import write_canonical_deployments


def test_dora_service_insufficient_data(tmp_path: Path) -> None:
    settings = Settings(
        raw_dir=tmp_path / "raw",
        canonical_dir=tmp_path / "canonical",
        github_repos=["firmsoil/gain"],
    )
    svc = DORAService(settings=settings)
    res = svc.calculate_dora(repository="firmsoil/gain")

    assert res.status == "insufficient_data"
    assert res.deployment_frequency.status == "insufficient_data"
    assert res.change_fail_rate.status == "insufficient_data"
    assert "GitHub Deployments API" in res.missing_dependencies[0]


def test_dora_service_with_deployments(tmp_path: Path) -> None:
    canonical_dir = tmp_path / "canonical"
    settings = Settings(
        raw_dir=tmp_path / "raw",
        canonical_dir=canonical_dir,
        github_repos=["firmsoil/gain"],
    )

    # 4 deployments: 3 successful, 1 failed over a 7-day span
    t1_commit = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
    t1_deploy = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    t2_deploy = datetime(2026, 1, 3, 14, 0, 0, tzinfo=UTC)  # Failed
    t3_deploy = datetime(2026, 1, 3, 16, 0, 0, tzinfo=UTC)  # Remediation
    t4_deploy = datetime(2026, 1, 8, 12, 0, 0, tzinfo=UTC)

    commits = [
        CanonicalCommit(
            sha="c1",
            repository_name_with_owner="firmsoil/gain",
            author_name="Alice",
            committed_at=t1_commit,
            message="Feature commit",
            collected_at=datetime.now(UTC),
            ingestion_run_id="run-1",
        )
    ]
    write_canonical_commits(commits, canonical_dir / "commits__01.parquet")

    deps = [
        CanonicalDeployment(
            id="dep-1",
            source_system=SourceSystem.GITHUB,
            repository_name_with_owner="firmsoil/gain",
            environment=DeploymentEnvironment.PRODUCTION,
            status=DeploymentStatus.SUCCESS,
            commit_sha="c1",
            started_at=datetime(2026, 1, 1, 11, 55, 0, tzinfo=UTC),
            completed_at=t1_deploy,
            collected_at=datetime.now(UTC),
            ingestion_run_id="run-1",
        ),
        CanonicalDeployment(
            id="dep-2",
            source_system=SourceSystem.GITHUB,
            repository_name_with_owner="firmsoil/gain",
            environment=DeploymentEnvironment.PRODUCTION,
            status=DeploymentStatus.FAILURE,
            commit_sha="c2",
            started_at=datetime(2026, 1, 3, 13, 50, 0, tzinfo=UTC),
            completed_at=t2_deploy,
            collected_at=datetime.now(UTC),
            ingestion_run_id="run-1",
        ),
        CanonicalDeployment(
            id="dep-3",
            source_system=SourceSystem.GITHUB,
            repository_name_with_owner="firmsoil/gain",
            environment=DeploymentEnvironment.PRODUCTION,
            status=DeploymentStatus.SUCCESS,
            commit_sha="c3",
            started_at=datetime(2026, 1, 3, 15, 50, 0, tzinfo=UTC),
            completed_at=t3_deploy,
            collected_at=datetime.now(UTC),
            ingestion_run_id="run-1",
        ),
        CanonicalDeployment(
            id="dep-4",
            source_system=SourceSystem.GITHUB,
            repository_name_with_owner="firmsoil/gain",
            environment=DeploymentEnvironment.PRODUCTION,
            status=DeploymentStatus.SUCCESS,
            commit_sha="c4",
            started_at=datetime(2026, 1, 8, 11, 55, 0, tzinfo=UTC),
            completed_at=t4_deploy,
            collected_at=datetime.now(UTC),
            ingestion_run_id="run-1",
        ),
    ]
    write_canonical_deployments(deps, canonical_dir / "deployments__01.parquet")

    svc = DORAService(settings=settings)
    res = svc.calculate_dora(repository="firmsoil/gain")

    assert res.status == "available"
    assert res.deployment_frequency.status == "available"
    assert res.deployment_frequency.value == 3.0  # 3 successes / 7 days * 7 = 3.0/wk
    assert res.change_fail_rate.status == "available"
    assert res.change_fail_rate.value == 25.0  # 1 fail / 4 total = 25%
    # Lead time for dep-1 with commit c1: 10:00 to 12:00 = 7200s
    assert res.change_lead_time.status == "available"
    # Recovery time for dep-2 (failure completed 14:00) to dep-3
    # (success completed 16:00): 2h = 7200s
    assert res.failed_deployment_recovery_time.status == "available"
    assert res.failed_deployment_recovery_time.value == 7200.0
