"""Tests for CanonicalIssue domain model and Parquet persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from gain.model.issue import (
    CanonicalIssue,
    IssueStatus,
    IssueType,
    SourceSystem,
)
from gain.storage.issues import (
    load_issues_for_project_or_repo,
    read_canonical_issues,
    write_canonical_issues,
)


def test_canonical_issue_validation() -> None:
    created = datetime(2026, 1, 10, 10, 0, 0, tzinfo=UTC)
    resolved = datetime(2026, 1, 10, 14, 0, 0, tzinfo=UTC)

    issue = CanonicalIssue(
        id="jira:ENG-101",
        key="ENG-101",
        source_system=SourceSystem.JIRA,
        project_key="ENG",
        title="Implement OAuth authentication flow",
        issue_type=IssueType.STORY,
        status=IssueStatus.DONE,
        created_at=created,
        updated_at=resolved,
        resolved_at=resolved,
        collected_at=datetime.now(UTC),
        ingestion_run_id="run-1",
    )

    assert issue.is_resolved is True
    assert issue.cycle_time_seconds() == 14400.0  # 4 hours = 14,400s
    record = issue.to_record()
    assert record["key"] == "ENG-101"
    assert record["source_system"] == "jira"


def test_canonical_issue_storage_roundtrip(tmp_path: Path) -> None:
    created = datetime(2026, 1, 10, 10, 0, 0, tzinfo=UTC)
    resolved = datetime(2026, 1, 10, 12, 0, 0, tzinfo=UTC)

    issue = CanonicalIssue(
        id="linear:ENG-102",
        key="ENG-102",
        source_system=SourceSystem.LINEAR,
        project_key="ENG",
        title="Fix rate limit backoff",
        issue_type=IssueType.BUG,
        status=IssueStatus.DONE,
        created_at=created,
        updated_at=resolved,
        resolved_at=resolved,
        collected_at=datetime.now(UTC),
        ingestion_run_id="run-2",
    )

    parquet_file = tmp_path / "issues__linear__run-2.parquet"
    write_canonical_issues([issue], parquet_file)

    loaded = read_canonical_issues(parquet_file)
    assert len(loaded) == 1
    assert loaded[0].id == "linear:ENG-102"
    assert loaded[0].cycle_time_seconds() == 7200.0

    filtered = load_issues_for_project_or_repo("ENG", canonical_dir=tmp_path)
    assert len(filtered) == 1
