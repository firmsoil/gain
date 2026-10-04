"""Tests for Verification Tax (GAIN-QUAL-005) and Defect Rework (GAIN-QUAL-006) metrics,
and the universal repository scan CLI command.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from gain.cli import app
from gain.config import Settings
from gain.metrics.catalog import MetricCatalog
from gain.metrics.defect_churn import DefectReworkMetric
from gain.metrics.verification_tax import VerificationTaxMetric
from gain.model.pr import PullRequest
from gain.services.metrics import MetricService
from gain.storage.analytics import write_canonical

runner = CliRunner()


def make_test_pr_with_timing(
    node_id: str,
    number: int,
    created_at: datetime,
    merged_at: datetime | None,
    author: str = "alice",
    additions: int = 50,
    deletions: int = 10,
    changed_files: int = 2,
    review_decision: str = "APPROVED",
    repo: str = "firmsoil/gain",
) -> PullRequest:
    return PullRequest(
        github_node_id=node_id,
        number=number,
        repository_name_with_owner=repo,
        repository_id="R_123",
        author_login=author,
        author_type="User",
        created_at=created_at,
        closed_at=merged_at,
        merged_at=merged_at,
        state="MERGED" if merged_at else "OPEN",
        is_draft=False,
        additions=additions,
        deletions=deletions,
        changed_files=changed_files,
        review_decision=review_decision,
        collected_at=datetime.now(UTC),
        ingestion_run_id="run-test",
    )


def test_verification_tax_metric_catalog_registration() -> None:
    catalog = MetricCatalog(Path("docs/metrics/metric-catalog.yaml"))
    meta = catalog.get("GAIN-QUAL-005")
    assert meta["metric_id"] == "GAIN-QUAL-005"
    assert meta["name"] == "verification_tax_index"
    assert meta["type"] == "distribution"
    assert "review_latency" in meta["formula"]


def test_verification_tax_calculation() -> None:
    base_time = datetime(2026, 3, 1, 10, 0, tzinfo=UTC)
    prs = [
        # PR 1: 2 hours latency
        make_test_pr_with_timing("PR_1", 1, base_time, base_time + timedelta(hours=2)),
        # PR 2: 50 hours latency (exceeds 48h friction threshold)
        make_test_pr_with_timing("PR_2", 2, base_time, base_time + timedelta(hours=50)),
        # PR 3: 4 hours latency
        make_test_pr_with_timing("PR_3", 3, base_time, base_time + timedelta(hours=4)),
        # PR 4: Open PR (not merged) -> skipped
        make_test_pr_with_timing("PR_4", 4, base_time, None),
    ]

    obs = VerificationTaxMetric.observations(prs, high_friction_threshold_hours=48.0)
    assert len(obs) == 3

    assert obs[0].review_latency_hours == 2.0
    assert obs[0].is_high_friction is False

    assert obs[1].review_latency_hours == 50.0
    assert obs[1].is_high_friction is True

    summary = VerificationTaxMetric.summary(obs, total_prs=len(prs))
    assert summary["total_observations"] == 3
    assert summary["total_evaluated_prs"] == 4
    # Latencies: 2 + 50 + 4 = 56 / 3 = 18.67
    assert summary["mean_latency_hours"] == 18.67
    assert summary["high_friction_pr_count"] == 1
    assert summary["high_friction_percentage"] == 25.0


def test_defect_rework_metric_catalog_registration() -> None:
    catalog = MetricCatalog(Path("docs/metrics/metric-catalog.yaml"))
    meta = catalog.get("GAIN-QUAL-006")
    assert meta["metric_id"] == "GAIN-QUAL-006"
    assert meta["name"] == "defect_rework_rate"
    assert meta["type"] == "ratio"
    assert "followup_rework_churn" in meta["formula"]


def test_defect_rework_calculation() -> None:
    base_time = datetime(2026, 3, 1, 10, 0, tzinfo=UTC)
    prs = [
        # PR 1: merged at day 0
        make_test_pr_with_timing(
            "PR_1",
            1,
            base_time,
            base_time + timedelta(hours=2),
            author="alice",
            additions=100,
            deletions=10,
        ),
        # PR 2: merged at day 1 (within 14d window of PR 1)
        make_test_pr_with_timing(
            "PR_2",
            2,
            base_time + timedelta(days=1),
            base_time + timedelta(days=1, hours=2),
            author="bob",
            additions=20,
            deletions=5,
        ),
        # PR 3: merged at day 30 (outside 14d window of PR 1)
        make_test_pr_with_timing(
            "PR_3",
            3,
            base_time + timedelta(days=30),
            base_time + timedelta(days=30, hours=2),
            author="charlie-fix-bot",
            additions=10,
            deletions=2,
        ),
    ]

    obs = DefectReworkMetric.observations(prs, window_days=14)
    assert len(obs) == 3

    # PR 1 has 1 follow-up within 14 days (PR 2 with additions=20, deletions=5 -> churn=25)
    assert obs[0].followup_rework_count == 1
    assert obs[0].followup_rework_churn == 25
    assert obs[0].is_hotfix is False

    # PR 3 author matches fix bot pattern
    assert obs[2].is_hotfix is True

    summary = DefectReworkMetric.summary(obs, total_prs=len(prs))
    assert summary["total_observations"] == 3
    assert summary["hotfix_pr_count"] == 1
    # 1 out of 3 = 33.33%
    assert summary["hotfix_percentage"] == 33.33
    assert summary["total_followup_rework_churn"] == 25


def test_metric_service_queries(tmp_path: Path) -> None:
    canonical_dir = tmp_path / "canonical"
    canonical_dir.mkdir(parents=True, exist_ok=True)
    base_time = datetime(2026, 3, 1, 10, 0, tzinfo=UTC)

    prs = [
        make_test_pr_with_timing("PR_1", 1, base_time, base_time + timedelta(hours=2)),
        make_test_pr_with_timing("PR_2", 2, base_time, base_time + timedelta(hours=10)),
    ]
    write_canonical(prs, canonical_dir / "prs.parquet")

    settings = Settings(canonical_dir=canonical_dir)
    service = MetricService(settings=settings)
    vt_res = service.query_verification_tax("firmsoil/gain")
    assert vt_res.total_evaluated == 2
    assert vt_res.merged_count == 2
    assert vt_res.summary_stats["mean_latency_hours"] == 6.0

    dr_res = service.query_defect_rework("firmsoil/gain")
    assert dr_res.total_evaluated == 2
    assert dr_res.merged_count == 2


def test_cli_scan_command(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    canonical_dir = tmp_path / "canonical"
    canonical_dir.mkdir(parents=True, exist_ok=True)
    base_time = datetime(2026, 3, 1, 10, 0, tzinfo=UTC)

    prs = [
        make_test_pr_with_timing("PR_1", 1, base_time, base_time + timedelta(hours=2)),
    ]
    write_canonical(prs, canonical_dir / "prs.parquet")

    settings = Settings(
        raw_dir=tmp_path / "raw",
        canonical_dir=canonical_dir,
        metrics_dir=tmp_path / "metrics",
        output_dir=tmp_path / "output",
        data_dir=tmp_path / "data",
    )
    settings.ensure_directories()
    monkeypatch.setattr("gain.cli.get_settings", lambda: settings)
    monkeypatch.setattr("gain.cli.scan.get_settings", lambda: settings)

    # 1. Markdown output
    result_md = runner.invoke(app, ["scan", ".", "--format", "markdown"])
    assert result_md.exit_code == 0
    assert "GAIN AI-Native Software Engineering (SE 3.0) Scorecard" in result_md.stdout
    assert "Verification Tax" in result_md.stdout

    # 2. JSON output
    result_json = runner.invoke(app, ["scan", ".", "--format", "json"])
    assert result_json.exit_code == 0
    data = json.loads(result_json.stdout)
    assert data["repository"] == "firmsoil/gain"
    assert "telemetry_overview" in data
    assert "verification_and_stability" in data
