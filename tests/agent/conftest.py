"""Test fixtures for GAIN Engineering Intelligence Agent test suite."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from gain.config import Settings, set_settings_override
from gain.mcp.auth.context import DEV_PRINCIPAL, set_current_principal
from gain.model.pr import PullRequest
from gain.storage.analytics import write_canonical


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    output_dir = tmp_path / "data"
    raw_dir = output_dir / "raw"
    canonical_dir = output_dir / "canonical"
    metrics_dir = output_dir / "metrics"
    requirements_dir = output_dir / "requirements"
    spec_dir = output_dir / "specs"

    return Settings(
        github_token="ghp_testtoken1234567890abcdef",
        output_dir=output_dir,
        raw_dir=raw_dir,
        canonical_dir=canonical_dir,
        metrics_dir=metrics_dir,
        requirements_dir=requirements_dir,
        specification_seed_dir=spec_dir,
    )


@pytest.fixture
def sample_prs() -> list[PullRequest]:
    return [
        PullRequest(
            github_node_id="PR_kwDOABC1234",
            number=101,
            repository_name_with_owner="firmsoil/gain",
            repository_id="R_kgDOABC123",
            author_login="lead-dev",
            author_type="User",
            created_at=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
            closed_at=datetime(2026, 1, 1, 14, 0, tzinfo=UTC),
            merged_at=datetime(2026, 1, 1, 14, 0, tzinfo=UTC),
            state="MERGED",
            is_draft=False,
            additions=120,
            deletions=30,
            changed_files=4,
            review_decision="APPROVED",
            collected_at=datetime(2026, 1, 2, 0, 0, tzinfo=UTC),
            ingestion_run_id="run-test-001",
        ),
        PullRequest(
            github_node_id="PR_kwDOABC5678",
            number=102,
            repository_name_with_owner="firmsoil/gain",
            repository_id="R_kgDOABC123",
            author_login="junior-dev",
            author_type="User",
            created_at=datetime(2026, 1, 2, 8, 0, tzinfo=UTC),
            closed_at=datetime(2026, 1, 3, 8, 0, tzinfo=UTC),
            merged_at=datetime(2026, 1, 3, 8, 0, tzinfo=UTC),
            state="MERGED",
            is_draft=False,
            additions=45,
            deletions=10,
            changed_files=2,
            review_decision="APPROVED",
            collected_at=datetime(2026, 1, 4, 0, 0, tzinfo=UTC),
            ingestion_run_id="run-test-001",
        ),
    ]


@pytest.fixture
def populated_env(
    test_settings: Settings, sample_prs: list[PullRequest]
) -> Generator[Settings, None, None]:
    test_settings.canonical_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = test_settings.canonical_dir / "prs__test.parquet"
    write_canonical(sample_prs, parquet_path)
    set_settings_override(test_settings)
    yield test_settings
    set_settings_override(None)


@pytest.fixture(autouse=True)
def reset_principal() -> Generator[None, None, None]:
    set_current_principal(DEV_PRINCIPAL)
    yield
    set_current_principal(DEV_PRINCIPAL)
