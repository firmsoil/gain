"""Unit and integration tests for in-tree AI attribution detector and local git adapter."""

import subprocess
from datetime import UTC, datetime
from pathlib import Path

from gain.adapters.git_local import LocalGitSourceAdapter
from gain.attribution.detector import AIAttributionDetector
from gain.attribution.models import AttributionSignalType
from gain.config import Settings
from gain.model.ai import AiToolType
from gain.model.commit import CanonicalCommit
from gain.model.pr import PullRequest
from gain.services.ai_impact import AIImpactService
from gain.storage.analytics import write_canonical


def test_ai_attribution_detector_trailers() -> None:
    detector = AIAttributionDetector()
    now = datetime.now(UTC)

    copilot_commit = CanonicalCommit(
        sha="1111111111111111111111111111111111111111",
        repository_name_with_owner="firmsoil/gain",
        author_name="Alice Dev",
        author_login="alice",
        committed_at=now,
        message="feat: add telemetry\n\nCo-authored-by: GitHub Copilot <copilot@github.com>",
        additions=50,
        deletions=10,
        files_changed=2,
        collected_at=now,
        ingestion_run_id="run-1",
    )

    signals = detector.detect_commit_signals(copilot_commit)
    assert len(signals) >= 1
    assert any(
        s.tool_type == AiToolType.COPILOT and s.signal_type == AttributionSignalType.TRAILER
        for s in signals
    )

    claude_commit = CanonicalCommit(
        sha="2222222222222222222222222222222222222222",
        repository_name_with_owner="firmsoil/gain",
        author_name="Bob Dev",
        author_login="bob",
        committed_at=now,
        message="refactor: clean models\n\nCo-authored-by: Claude <claude@anthropic.com>",
        additions=20,
        deletions=40,
        files_changed=1,
        collected_at=now,
        ingestion_run_id="run-1",
    )
    claude_signals = detector.detect_commit_signals(claude_commit)
    assert any(s.tool_type == AiToolType.CLAUDE_DEV for s in claude_signals)

    cursor_commit = CanonicalCommit(
        sha="3333333333333333333333333333333333333333",
        repository_name_with_owner="firmsoil/gain",
        author_name="Charlie Dev",
        author_login="charlie",
        committed_at=now,
        message="feat: cursor composer feature\n\nGenerated with Cursor Composer",
        additions=120,
        deletions=5,
        files_changed=3,
        collected_at=now,
        ingestion_run_id="run-1",
    )
    cursor_signals = detector.detect_commit_signals(cursor_commit)
    assert any(s.tool_type == AiToolType.CURSOR for s in cursor_signals)


def test_ai_attribution_detector_bots() -> None:
    detector = AIAttributionDetector()
    now = datetime.now(UTC)

    pr_bot = PullRequest(
        github_node_id="pr_node_1",
        number=42,
        repository_name_with_owner="firmsoil/gain",
        repository_id="repo_1",
        author_login="copilot[bot]",
        author_type="Bot",
        created_at=now,
        merged_at=now,
        state="MERGED",
        is_draft=False,
        additions=100,
        deletions=20,
        changed_files=2,
        collected_at=now,
        ingestion_run_id="run-1",
    )

    signals = detector.detect_pr_signals(pr_bot)
    assert len(signals) == 1
    assert signals[0].tool_type == AiToolType.COPILOT
    assert signals[0].signal_type == AttributionSignalType.BOT_AUTHOR


def test_attribution_report_and_telemetry_synthesis() -> None:
    detector = AIAttributionDetector()
    now = datetime.now(UTC)

    commits = [
        CanonicalCommit(
            sha="c1",
            repository_name_with_owner="org/repo",
            author_name="Alice",
            author_login="alice",
            committed_at=now,
            message="Co-authored-by: GitHub Copilot <copilot@github.com>",
            additions=100,
            deletions=10,
            files_changed=1,
            collected_at=now,
            ingestion_run_id="r1",
        ),
        CanonicalCommit(
            sha="c2",
            repository_name_with_owner="org/repo",
            author_name="Bob",
            author_login="bob",
            committed_at=now,
            message="Standard manual commit without AI",
            additions=50,
            deletions=20,
            files_changed=1,
            collected_at=now,
            ingestion_run_id="r1",
        ),
    ]

    prs = [
        PullRequest(
            github_node_id="p1",
            number=1,
            repository_name_with_owner="org/repo",
            repository_id="r_id",
            author_login="alice",
            created_at=now,
            merged_at=now,
            state="MERGED",
            is_draft=False,
            additions=100,
            deletions=10,
            changed_files=1,
            collected_at=now,
            ingestion_run_id="r1",
        ),
        PullRequest(
            github_node_id="p2",
            number=2,
            repository_name_with_owner="org/repo",
            repository_id="r_id",
            author_login="bob",
            created_at=now,
            merged_at=now,
            state="MERGED",
            is_draft=False,
            additions=50,
            deletions=20,
            changed_files=1,
            collected_at=now,
            ingestion_run_id="r1",
        ),
    ]

    report = detector.analyze_repository("org/repo", prs, commits)
    assert report.total_prs == 2
    assert report.ai_assisted_prs == 1
    assert report.ai_penetration_rate == 0.5
    assert "alice" in report.ai_active_developers
    assert "bob" not in report.ai_active_developers

    telemetry = detector.synthesize_developer_telemetry("org/repo", prs, commits)
    assert len(telemetry) == 2
    alice_t = next(t for t in telemetry if t.developer_id == "alice")
    bob_t = next(t for t in telemetry if t.developer_id == "bob")
    assert alice_t.is_ai_active is True
    assert bob_t.is_ai_active is False


def test_local_git_source_adapter(tmp_path: Path) -> None:
    # Initialize a temporary git repository
    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=repo_dir, check=True)

    test_file = repo_dir / "app.py"
    test_file.write_text("print('hello world')\n")
    subprocess.run(["git", "add", "app.py"], cwd=repo_dir, check=True)
    subprocess.run(
        [
            "git",
            "commit",
            "-m",
            "feat: initial commit\n\nCo-authored-by: GitHub Copilot <bot@gh.com>",
        ],
        cwd=repo_dir,
        check=True,
    )

    settings = Settings(
        raw_dir=tmp_path / "raw",
        canonical_dir=tmp_path / "canonical",
        metrics_dir=tmp_path / "metrics",
        output_dir=tmp_path / "output",
        github_repos=["test/repo"],
    )
    adapter = LocalGitSourceAdapter(settings)
    assert adapter.is_git_repository(repo_dir) is True
    assert adapter.is_git_repository(tmp_path / "nonexistent") is False

    commits = adapter.extract_commits(repo_dir)
    assert len(commits) == 1
    assert commits[0].author_name == "Tester"
    assert "Co-authored-by: GitHub Copilot" in commits[0].message

    prs = adapter.extract_pull_requests(repo_dir, commits=commits)
    assert len(prs) == 1
    assert prs[0].merged is True

    result = adapter.ingest_local_repository(repo_dir)
    assert result["total_commits"] == 1
    assert result["total_prs"] == 1
    assert result["ai_assisted_prs"] == 1
    assert Path(result["canonical_pr_path"]).exists()
    assert Path(result["canonical_telemetry_path"]).exists()


def test_ai_impact_service_in_tree_fallback(tmp_path: Path) -> None:
    settings = Settings(
        raw_dir=tmp_path / "raw",
        canonical_dir=tmp_path / "canonical",
        metrics_dir=tmp_path / "metrics",
        output_dir=tmp_path / "output",
        github_repos=["test_org/test_repo"],
    )
    settings.ensure_directories()
    repo_name = "test_org/test_repo"
    now = datetime.now(UTC)

    # PR 1: AI-assisted author (copilot[bot])
    pr1 = PullRequest(
        github_node_id="p1",
        number=1,
        repository_name_with_owner=repo_name,
        repository_id="r1",
        author_login="copilot[bot]",
        author_type="Bot",
        created_at=now,
        merged_at=now,
        state="MERGED",
        is_draft=False,
        additions=200,
        deletions=10,
        changed_files=2,
        collected_at=now,
        ingestion_run_id="run-1",
    )
    # PR 2: Baseline human author
    pr2 = PullRequest(
        github_node_id="p2",
        number=2,
        repository_name_with_owner=repo_name,
        repository_id="r1",
        author_login="human_dev",
        author_type="User",
        created_at=now,
        merged_at=now,
        state="MERGED",
        is_draft=False,
        additions=50,
        deletions=40,
        changed_files=2,
        collected_at=now,
        ingestion_run_id="run-1",
    )

    write_canonical([pr1, pr2], settings.canonical_dir / "pull_requests__01.parquet")

    service = AIImpactService(settings)
    # Notice: No ai_telemetry file was pre-created! Service should fallback to in-tree detection.
    impact_res = service.analyze_impact(repository=repo_name)
    assert impact_res.status == "available"
    assert impact_res.cohort_definition["ai_active_developers"] >= 1

    bloat_res = service.analyze_code_bloat_impact(repository=repo_name)
    assert bloat_res.status == "available"
    assert len(bloat_res.findings) >= 2
