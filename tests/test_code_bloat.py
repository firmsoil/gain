"""Tests for Refactoring Ratio (GAIN-QUAL-003) and Code Bloat Index (GAIN-QUAL-004)."""

from datetime import UTC, datetime
from pathlib import Path

from gain.config import Settings
from gain.metrics.catalog import MetricCatalog
from gain.metrics.code_bloat import (
    CodeBloatMetric,
    RefactoringRatioMetric,
)
from gain.model.ai import AiDeveloperTelemetry
from gain.model.pr import PullRequest
from gain.services.ai_impact import AIImpactService
from gain.services.metrics import MetricService
from gain.storage.ai_telemetry import write_ai_telemetry
from gain.storage.analytics import write_canonical


def make_test_pr(
    node_id: str,
    number: int,
    additions: int,
    deletions: int,
    changed_files: int,
    author: str = "alice",
    repo: str = "firmsoil/gain",
) -> PullRequest:
    now = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    return PullRequest(
        github_node_id=node_id,
        number=number,
        repository_name_with_owner=repo,
        repository_id="R_123",
        author_login=author,
        author_type="User",
        created_at=now,
        closed_at=now,
        merged_at=now,
        state="MERGED",
        is_draft=False,
        additions=additions,
        deletions=deletions,
        changed_files=changed_files,
        review_decision="APPROVED",
        collected_at=now,
        ingestion_run_id="run-test",
    )


def test_refactoring_ratio_metric_calculations() -> None:
    prs = [
        make_test_pr("PR_1", 1, additions=100, deletions=0, changed_files=2),  # Pure addition
        make_test_pr("PR_2", 2, additions=0, deletions=50, changed_files=1),  # Pure deletion
        make_test_pr("PR_3", 3, additions=50, deletions=50, changed_files=2),  # Balanced (0.5)
        # Refactoring cleanup (0.8):
        make_test_pr("PR_4", 4, additions=20, deletions=80, changed_files=3),
        # Empty diff (skipped):
        make_test_pr("PR_5", 5, additions=0, deletions=0, changed_files=0),
    ]

    obs = RefactoringRatioMetric.observations(prs)
    assert len(obs) == 4

    # PR 1
    assert obs[0].refactoring_ratio == 0.0
    assert obs[0].additive_ratio == 1.0
    assert obs[0].is_pure_addition is True

    # PR 2
    assert obs[1].refactoring_ratio == 1.0
    assert obs[1].additive_ratio == 0.0
    assert obs[1].is_pure_addition is False

    # PR 3
    assert obs[2].refactoring_ratio == 0.5
    assert obs[2].additive_ratio == 0.5
    assert obs[2].is_pure_addition is False

    # PR 4
    assert obs[3].refactoring_ratio == 0.8
    assert obs[3].additive_ratio == 0.2
    assert obs[3].is_pure_addition is False

    # Summary
    summary = RefactoringRatioMetric.summary(obs, total_prs=len(prs))
    assert summary["count"] == 4
    assert summary["total_evaluated"] == 5
    assert summary["total_additions"] == 170
    assert summary["total_deletions"] == 180
    assert summary["total_churn"] == 350
    # 180 / 350 = 0.5143
    assert summary["aggregate_refactoring_ratio"] == 0.5143
    assert summary["pure_addition_count"] == 1
    assert summary["pure_addition_percentage"] == 25.0
    assert summary["p50_refactoring_ratio"] is not None


def test_code_bloat_metric_density_and_threshold() -> None:
    prs = [
        # Bloated PR: 600 additions, 20 deletions across 1 file -> 580 net per file
        make_test_pr("PR_BLOAT", 10, additions=600, deletions=20, changed_files=1),
        # Clean modular PR: 80 additions, 60 deletions across 4 files -> 5 net per file
        make_test_pr("PR_CLEAN", 11, additions=80, deletions=60, changed_files=4),
        # Moderate PR: 150 additions, 10 deletions across 2 files -> 70 net per file
        make_test_pr("PR_MOD", 12, additions=150, deletions=10, changed_files=2),
    ]

    obs = CodeBloatMetric.observations(prs, bloat_expansion_threshold=100.0)
    assert len(obs) == 3

    assert obs[0].net_additions == 580
    assert obs[0].net_additions_per_file == 580.0
    assert obs[0].is_bloat_flagged is True

    assert obs[1].net_additions == 20
    assert obs[1].net_additions_per_file == 5.0
    assert obs[1].is_bloat_flagged is False

    assert obs[2].net_additions == 140
    assert obs[2].net_additions_per_file == 70.0
    assert obs[2].is_bloat_flagged is False

    summary = CodeBloatMetric.summary(obs)
    assert summary["count"] == 3
    assert summary["total_net_additions"] == 740
    assert summary["total_changed_files"] == 7
    # 740 / 7 = 105.71
    assert summary["aggregate_net_additions_per_file"] == 105.71
    assert summary["bloat_flag_count"] == 1
    assert summary["bloat_flag_percentage"] == 33.33


def test_metric_catalog_contains_qual_metrics() -> None:
    catalog = MetricCatalog(Path("docs/metrics/metric-catalog.yaml"))

    qual_003 = catalog.get("GAIN-QUAL-003")
    assert qual_003["metric_id"] == "GAIN-QUAL-003"
    assert qual_003["name"] == "refactoring_vs_additive_churn_ratio"
    assert qual_003["type"] == "ratio"
    assert qual_003["formula"] == "deletions / (additions + deletions)"

    qual_004 = catalog.get("GAIN-QUAL-004")
    assert qual_004["metric_id"] == "GAIN-QUAL-004"
    assert qual_004["name"] == "code_bloat_index"
    assert qual_004["type"] == "distribution"
    assert qual_004["formula"] == "net_additions / max(1, changed_files)"


def test_metric_service_query_bloat_and_refactoring(tmp_path: Path) -> None:
    canonical_dir = tmp_path / "canonical"
    canonical_dir.mkdir(parents=True, exist_ok=True)
    settings = Settings(canonical_dir=canonical_dir)

    prs = [
        make_test_pr("PR_101", 101, additions=200, deletions=0, changed_files=1),
        make_test_pr("PR_102", 102, additions=50, deletions=50, changed_files=2),
    ]
    write_canonical(prs, canonical_dir / "pull_requests__01.parquet")

    service = MetricService(settings=settings)

    refactor_res = service.query_refactoring_ratio(repository="firmsoil/gain")
    assert refactor_res.metric_id == "GAIN-QUAL-003"
    assert refactor_res.total_evaluated == 2
    assert refactor_res.summary_stats["pure_addition_count"] == 1

    bloat_res = service.query_code_bloat(
        repository="firmsoil/gain", bloat_expansion_threshold=100.0
    )
    assert bloat_res.metric_id == "GAIN-QUAL-004"
    assert bloat_res.total_evaluated == 2
    assert bloat_res.summary_stats["bloat_flag_count"] == 1


def test_ai_impact_service_analyze_code_bloat_impact(tmp_path: Path) -> None:
    canonical_dir = tmp_path / "canonical"
    canonical_dir.mkdir(parents=True, exist_ok=True)
    settings = Settings(canonical_dir=canonical_dir)

    # 1. Telemetry: 'ai-user' is active AI developer
    telemetry = [
        AiDeveloperTelemetry(
            developer_id="ai-user",
            repository="firmsoil/gain",
            suggestions_count=500,
            acceptances_count=200,
            is_ai_active=True,
        )
    ]
    write_ai_telemetry(telemetry, canonical_dir / "ai_telemetry__01.parquet")

    # 2. PRs: AI user has pure additions and high bloat; baseline has balanced refactoring
    prs = [
        make_test_pr(
            "PR_AI",
            201,
            additions=400,
            deletions=0,
            changed_files=1,
            author="ai-user",
        ),
        make_test_pr(
            "PR_BASE",
            202,
            additions=60,
            deletions=50,
            changed_files=2,
            author="base-user",
        ),
    ]
    write_canonical(prs, canonical_dir / "pull_requests__01.parquet")

    impact_svc = AIImpactService(settings=settings)
    bloat_impact = impact_svc.analyze_code_bloat_impact(repository="firmsoil/gain")

    assert bloat_impact.status == "available"
    assert bloat_impact.cohort_definition["ai_active_developers"] == 1
    assert bloat_impact.cohort_definition["ai_prs_evaluated"] == 1
    assert bloat_impact.comparison_cohort is not None
    assert bloat_impact.comparison_cohort["baseline_prs_evaluated"] == 1

    # Findings should flag the SE 2.0 additive churn bias and bloat
    findings_text = " ".join(bloat_impact.findings)
    assert "GAIN-QUAL-003" in findings_text
    assert "GAIN-QUAL-004" in findings_text
    assert "Hassan et al. (2026)" in findings_text
