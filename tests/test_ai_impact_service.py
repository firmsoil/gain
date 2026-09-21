"""Tests for deterministic AIImpactService."""

from datetime import UTC, datetime
from pathlib import Path

from gain.config import Settings
from gain.mcp.schemas.ai import ClaimClassification
from gain.model.ai import AiDeveloperTelemetry
from gain.model.pr import PullRequest
from gain.services.ai_impact import AIImpactService
from gain.storage.ai_telemetry import write_ai_telemetry
from gain.storage.analytics import write_canonical


def test_ai_impact_service_without_telemetry(tmp_path: Path) -> None:
    settings = Settings(canonical_dir=tmp_path / "canonical")
    service = AIImpactService(settings=settings)

    result = service.analyze_impact(repository="firmsoil/gain")

    assert result.status == "insufficient_data"
    assert result.classification == ClaimClassification.UNKNOWN
    assert result.confidence_level == "Low"
    assert len(result.missing_dependencies) > 0


def test_ai_impact_service_with_telemetry_and_prs(tmp_path: Path) -> None:
    canonical_dir = tmp_path / "canonical"
    canonical_dir.mkdir(parents=True, exist_ok=True)
    settings = Settings(canonical_dir=canonical_dir)

    # 1. Store AI telemetry for 'lead-dev'
    telemetry = [
        AiDeveloperTelemetry(
            developer_id="lead-dev",
            repository="firmsoil/gain",
            suggestions_count=1000,
            acceptances_count=400,
            is_ai_active=True,
        ),
    ]
    write_ai_telemetry(telemetry, canonical_dir / "ai_telemetry__01.parquet")

    # 2. Store PRs: one by 'lead-dev' (AI cohort), one by 'junior-dev' (baseline cohort)
    prs = [
        PullRequest(
            github_node_id="PR_001",
            number=101,
            repository_name_with_owner="firmsoil/gain",
            repository_id="R_123",
            author_login="lead-dev",
            created_at=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
            merged_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
            state="MERGED",
            is_draft=False,
            additions=50,
            deletions=10,
            changed_files=2,
            collected_at=datetime(2026, 1, 2, 0, 0, tzinfo=UTC),
            ingestion_run_id="run-1",
        ),
        PullRequest(
            github_node_id="PR_002",
            number=102,
            repository_name_with_owner="firmsoil/gain",
            repository_id="R_123",
            author_login="junior-dev",
            created_at=datetime(2026, 1, 2, 8, 0, tzinfo=UTC),
            merged_at=datetime(2026, 1, 2, 14, 0, tzinfo=UTC),
            state="MERGED",
            is_draft=False,
            additions=55,
            deletions=15,
            changed_files=3,
            collected_at=datetime(2026, 1, 3, 0, 0, tzinfo=UTC),
            ingestion_run_id="run-1",
        ),
    ]
    write_canonical(prs, canonical_dir / "pull_requests__01.parquet")

    service = AIImpactService(settings=settings)
    result = service.analyze_impact(repository="firmsoil/gain")

    assert result.status == "available"
    assert result.classification == ClaimClassification.ASSOCIATED
    assert result.cohort_definition is not None
    assert result.cohort_definition["ai_active_developers"] == 1
    assert result.cohort_definition["ai_prs_evaluated"] == 1
    assert result.comparison_cohort is not None
    assert result.comparison_cohort["baseline_prs_evaluated"] == 1
    assert len(result.findings) == 2
    assert "Delta: -14400.0s" in result.findings[1]  # 2h vs 6h -> -4h = -14400s
