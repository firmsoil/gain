"""Tests for IssueAnalyticsService and cross-system PR traceability."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from gain.config import Settings
from gain.mcp.schemas.ai import ClaimClassification
from gain.model.issue import (
    CanonicalIssue,
    IssueStatus,
    IssueType,
    SourceSystem,
)
from gain.model.pr import PullRequest
from gain.services.issue_analytics import IssueAnalyticsService
from gain.storage.analytics import write_canonical
from gain.storage.issues import write_canonical_issues


def test_issue_analytics_empty(tmp_path: Path) -> None:
    settings = Settings(
        raw_dir=tmp_path / "raw",
        canonical_dir=tmp_path / "canonical",
        github_repos=["firmsoil/gain"],
    )
    svc = IssueAnalyticsService(settings=settings)
    res = svc.analyze_issues(project_key="ENG")

    assert res.status == "insufficient_data"
    assert res.classification == ClaimClassification.UNKNOWN
    assert res.total_issues == 0


def test_issue_analytics_and_traceability(tmp_path: Path) -> None:
    canonical_dir = tmp_path / "canonical"
    settings = Settings(
        raw_dir=tmp_path / "raw",
        canonical_dir=canonical_dir,
        github_repos=["firmsoil/gain"],
    )

    t0 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
    t1 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)  # 2h = 7200s
    t2 = datetime(2026, 1, 1, 14, 0, 0, tzinfo=UTC)  # 4h = 14400s

    issues = [
        CanonicalIssue(
            id="jira:ENG-1",
            key="ENG-1",
            source_system=SourceSystem.JIRA,
            project_key="ENG",
            title="First task",
            issue_type=IssueType.STORY,
            status=IssueStatus.DONE,
            created_at=t0,
            updated_at=t1,
            resolved_at=t1,
            linked_pr_keys=["101"],
            collected_at=datetime.now(UTC),
            ingestion_run_id="run-1",
        ),
        CanonicalIssue(
            id="jira:ENG-2",
            key="102",  # numeric key matches PR number 102
            source_system=SourceSystem.JIRA,
            project_key="ENG",
            title="Second task",
            issue_type=IssueType.BUG,
            status=IssueStatus.DONE,
            created_at=t0,
            updated_at=t2,
            resolved_at=t2,
            linked_pr_keys=[],
            collected_at=datetime.now(UTC),
            ingestion_run_id="run-1",
        ),
        CanonicalIssue(
            id="jira:ENG-3",
            key="ENG-3",
            source_system=SourceSystem.JIRA,
            project_key="ENG",
            title="Third task open",
            issue_type=IssueType.TASK,
            status=IssueStatus.OPEN,
            created_at=t0,
            updated_at=t0,
            resolved_at=None,
            linked_pr_keys=[],
            collected_at=datetime.now(UTC),
            ingestion_run_id="run-1",
        ),
    ]
    write_canonical_issues(issues, canonical_dir / "issues__jira__01.parquet")

    # Canonical PRs
    prs = [
        PullRequest(
            github_node_id="PR_101",
            number=101,
            repository_name_with_owner="firmsoil/gain",
            repository_id="R_1",
            author_login="alice",
            created_at=t0,
            merged_at=t1,
            state="MERGED",
            is_draft=False,
            collected_at=datetime.now(UTC),
            ingestion_run_id="run-1",
        ),
        PullRequest(
            github_node_id="PR_102",
            number=102,
            repository_name_with_owner="firmsoil/gain",
            repository_id="R_1",
            author_login="bob",
            created_at=t0,
            merged_at=t2,
            state="MERGED",
            is_draft=False,
            collected_at=datetime.now(UTC),
            ingestion_run_id="run-1",
        ),
    ]
    write_canonical(prs, canonical_dir / "pull_requests__01.parquet")

    svc = IssueAnalyticsService(settings=settings)
    res = svc.analyze_issues(project_key="ENG", repository="firmsoil/gain")

    assert res.status == "available"
    assert res.classification == ClaimClassification.DERIVED
    assert res.total_issues == 3
    assert res.resolved_issues == 2
    assert res.open_issues == 1
    # p50 cycle time of 7200s and 14400s -> 14400s or 7200s (index 1 of 2 = 14400s)
    assert res.cycle_time_stats["count"] == 2.0
    assert res.cycle_time_stats["mean_seconds"] == 10800.0
    # Traceability: 2 issues linked (ENG-1 via explicit link, 102 via number match) out of 3 = 66.7%
    assert res.linked_prs_count == 2
    assert res.traceability_rate == 66.7
    assert len(res.findings) == 3
