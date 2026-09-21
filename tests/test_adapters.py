"""Tests for enterprise source adapters (Jira, Linear, Deployments)."""

from __future__ import annotations

import json
from pathlib import Path

from gain.adapters.deployments import DeploymentSourceAdapter
from gain.adapters.jira import JiraSourceAdapter
from gain.adapters.linear import LinearSourceAdapter
from gain.config import Settings
from gain.model.deployment import DeploymentEnvironment, DeploymentStatus
from gain.model.issue import IssueStatus, IssueType, SourceSystem


def test_jira_source_adapter(tmp_path: Path) -> None:
    settings = Settings(
        raw_dir=tmp_path / "raw",
        canonical_dir=tmp_path / "canonical",
        github_repos=["firmsoil/gain"],
    )

    valid_payload = {
        "id": "10023",
        "key": "GAIN-101",
        "fields": {
            "summary": "Implement DORA metrics pipeline",
            "description": "Calculate deployment frequency",
            "issuetype": {"name": "Story"},
            "status": {"name": "Done", "statusCategory": {"key": "done"}},
            "priority": {"name": "High"},
            "reporter": {"displayName": "Alice Engineer"},
            "assignee": {"displayName": "Bob Developer"},
            "labels": ["analytics", "dora"],
            "customfield_10016": 5.0,
            "created": "2026-01-10T09:00:00.000Z",
            "updated": "2026-01-11T17:00:00.000Z",
            "resolutiondate": "2026-01-11T17:00:00.000Z",
        },
        "linked_prs": ["42"],
    }
    malformed_payload = {"invalid_record": True}  # Missing id and key

    adapter = JiraSourceAdapter(settings=settings)
    res = adapter.ingest_payloads([valid_payload, malformed_payload], partition_key="GAIN")

    assert res.raw_records_count == 2
    assert res.canonical_records_count == 1
    assert res.errors_count == 1
    assert res.errors[0]["record_index"] == 1

    # Check raw JSONL
    raw_path = Path(res.raw_file_path)
    assert raw_path.exists()
    lines = raw_path.read_text().strip().split("\n")
    assert len(lines) == 2
    record0 = json.loads(lines[0])
    assert record0["metadata"]["source_system"] == "jira"
    assert record0["payload"]["key"] == "GAIN-101"

    # Check canonical Parquet
    canonical_path = Path(res.canonical_file_path)
    assert canonical_path.exists()
    from gain.storage.issues import read_canonical_issues

    canonical_issues = read_canonical_issues(canonical_path)
    assert len(canonical_issues) == 1
    issue = canonical_issues[0]
    assert issue.key == "GAIN-101"
    assert issue.source_system == SourceSystem.JIRA
    assert issue.issue_type == IssueType.STORY
    assert issue.status == IssueStatus.DONE
    assert issue.story_points == 5.0
    assert issue.linked_pr_keys == ["42"]
    assert issue.cycle_time_seconds() == 115200.0  # 32 hours


def test_linear_source_adapter(tmp_path: Path) -> None:
    settings = Settings(
        raw_dir=tmp_path / "raw",
        canonical_dir=tmp_path / "canonical",
        github_repos=["firmsoil/gain"],
    )

    linear_payload = {
        "id": "lin-uuid-1",
        "identifier": "ENG-202",
        "title": "Fix memory leak in parser",
        "description": "Profile heap during large sync",
        "team": {"key": "ENG"},
        "state": {"name": "In Review", "type": "started"},
        "priority": 2,
        "estimate": 3.0,
        "creator": {"name": "Charlie"},
        "assignee": {"name": "Dana"},
        "labels": {"nodes": [{"name": "backend"}, {"name": "bug"}]},
        "createdAt": "2026-01-12T10:00:00Z",
        "updatedAt": "2026-01-12T12:00:00Z",
    }

    adapter = LinearSourceAdapter(settings=settings)
    res = adapter.ingest_payloads([linear_payload], partition_key="ENG")

    assert res.canonical_records_count == 1
    assert res.errors_count == 0

    from gain.storage.issues import read_canonical_issues

    issues = read_canonical_issues(Path(res.canonical_file_path))
    assert len(issues) == 1
    assert issues[0].key == "ENG-202"
    assert issues[0].status == IssueStatus.IN_REVIEW
    assert issues[0].priority == "High"
    assert issues[0].story_points == 3.0


def test_deployment_source_adapter(tmp_path: Path) -> None:
    settings = Settings(
        raw_dir=tmp_path / "raw",
        canonical_dir=tmp_path / "canonical",
        github_repos=["firmsoil/gain"],
    )

    dep_payload = {
        "id": "run-9988",
        "repository": "firmsoil/gain",
        "environment": "production",
        "status": "success",
        "commit_sha": "c0ffee1234567890abcdef1234567890abcdef12",
        "ref": "main",
        "deployed_by": "deploy-bot",
        "started_at": "2026-01-15T18:00:00Z",
        "completed_at": "2026-01-15T18:04:30Z",
    }

    adapter = DeploymentSourceAdapter(settings=settings)
    res = adapter.ingest_payloads([dep_payload], partition_key="gain")

    assert res.canonical_records_count == 1
    assert res.errors_count == 0

    from gain.storage.deployments import read_canonical_deployments

    deps = read_canonical_deployments(Path(res.canonical_file_path))
    assert len(deps) == 1
    assert deps[0].environment == DeploymentEnvironment.PRODUCTION
    assert deps[0].status == DeploymentStatus.SUCCESS
    assert deps[0].duration_seconds == 270.0
