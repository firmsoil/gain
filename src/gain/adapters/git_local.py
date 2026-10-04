"""Local Git repository source adapter (SE 3.0 Offline & Zero-Token Mode).

Allows GAIN to analyze any local git repository codebase directly without
requiring GitHub API tokens, internet connectivity, or rate limits.
"""

from __future__ import annotations

import re
import subprocess
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import structlog

from gain.attribution.detector import AIAttributionDetector
from gain.config import Settings, get_settings
from gain.model.commit import CanonicalCommit
from gain.model.pr import PullRequest
from gain.storage.ai_telemetry import write_ai_telemetry
from gain.storage.analytics import write_canonical
from gain.storage.commits import write_canonical_commits
from gain.util import parse_utc_datetime

log = structlog.get_logger(__name__)


class LocalGitSourceAdapter:
    """Extracts canonical PR and commit telemetry directly from a local git repository."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.attribution_detector = AIAttributionDetector()

    def is_git_repository(self, path: Path) -> bool:
        """Verify whether target directory is a valid git repository."""
        if not path.exists() or not path.is_dir():
            return False
        try:
            res = subprocess.run(
                ["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"],
                capture_output=True,
                text=True,
                check=False,
            )
            return res.returncode == 0 and res.stdout.strip() == "true"
        except Exception:
            return False

    def resolve_repository_name(self, path: Path) -> str:
        """Resolve repository name with owner from git remote origin or directory name."""
        try:
            res = subprocess.run(
                ["git", "-C", str(path), "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
                check=False,
            )
            if res.returncode == 0 and res.stdout.strip():
                url = res.stdout.strip()
                # Parse git@github.com:owner/repo.git or https://github.com/owner/repo.git
                match = re.search(r"[:/]([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.-]+?)(?:\.git)?$", url)
                if match:
                    return f"{match.group(1)}/{match.group(2)}"
        except Exception as exc:
            log.debug("git_remote_url_lookup_failed", exc_info=exc)

        # Fallback to local directory basename
        return f"local/{path.resolve().name}"

    def extract_commits(
        self,
        path: Path,
        days: int | None = None,
        max_count: int | None = None,
        run_id: str | None = None,
    ) -> list[CanonicalCommit]:
        """Extract git commits and line churn stats from local repository."""
        active_run_id = run_id or str(uuid.uuid4())
        repo_name = self.resolve_repository_name(path)
        cmd = [
            "git",
            "-C",
            str(path),
            "log",
            "--numstat",
            "--date=iso-strict",
            "--format=format:__RECORD_START__%x1f%H%x1f%an%x1f%ae%x1f%aI%x1f%B%x1f__BODY_END__",
        ]

        if days is not None and days > 0:
            since_date = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%d")
            cmd.append(f"--since={since_date}")

        if max_count is not None and max_count > 0:
            cmd.append(f"-n{max_count}")

        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
            raw_output = proc.stdout
        except subprocess.CalledProcessError as exc:
            log.error("git_log_command_failed", error=str(exc))
            return []

        commits: list[CanonicalCommit] = []
        collected_at = datetime.now(UTC)

        chunks = raw_output.split("__RECORD_START__\x1f")
        for chunk in chunks:
            if not chunk.strip():
                continue

            parts = chunk.split("\x1f")
            if len(parts) < 6:
                continue

            sha = parts[0].strip()
            author_name = parts[1].strip()
            author_email = parts[2].strip()
            date_str = parts[3].strip()
            body_and_stat = parts[4]

            # Split message body from numstat lines
            stat_part = ""
            message = body_and_stat
            if "__BODY_END__" in body_and_stat:
                msg_body, stat_part = body_and_stat.split("__BODY_END__", 1)
                message = msg_body.strip()

            additions = 0
            deletions = 0
            files_changed = 0

            for line in stat_part.strip().splitlines():
                stat_match = re.match(r"^(\d+|-)\s+(\d+|-)\s+(.*)$", line.strip())
                if stat_match:
                    files_changed += 1
                    add_str, del_str = stat_match.group(1), stat_match.group(2)
                    if add_str != "-":
                        additions += int(add_str)
                    if del_str != "-":
                        deletions += int(del_str)

            try:
                dt = parse_utc_datetime(date_str)
            except Exception:
                dt = datetime.now(UTC)

            # Extract login from email if GitHub noreply email
            author_login = None
            if author_email:
                noreply_match = re.match(
                    r"^(\d+\+)?([a-zA-Z0-9_-]+)@users\.noreply\.github\.com$", author_email
                )
                if noreply_match:
                    author_login = noreply_match.group(2)
                else:
                    author_login = author_email.split("@")[0]

            commits.append(
                CanonicalCommit(
                    sha=sha,
                    repository_name_with_owner=repo_name,
                    author_name=author_name,
                    author_email=author_email,
                    author_login=author_login,
                    committed_at=dt,
                    message=message,
                    additions=additions,
                    deletions=deletions,
                    files_changed=files_changed,
                    collected_at=collected_at,
                    ingestion_run_id=active_run_id,
                )
            )

        return commits

    def extract_pull_requests(
        self,
        path: Path,
        commits: list[CanonicalCommit] | None = None,
        run_id: str | None = None,
    ) -> list[PullRequest]:
        """Extract pull request lifecycle units from merge commits and squash records."""
        active_run_id = run_id or str(uuid.uuid4())
        repo_name = self.resolve_repository_name(path)
        all_commits = (
            commits if commits is not None else self.extract_commits(path, run_id=active_run_id)
        )

        prs: list[PullRequest] = []
        collected_at = datetime.now(UTC)

        pr_number_seq = 1
        for c in all_commits:
            pr_num: int | None = None

            # 1. GitHub Merge Commit format: Merge pull request #123 from ...
            merge_match = re.search(r"Merge pull request #(\d+)", c.message)
            if merge_match:
                pr_num = int(merge_match.group(1))

            # 2. GitHub Squash format: Commit title (#123)
            squash_match = re.search(r"\(#(\d+)\)$", c.message.splitlines()[0].strip())
            if not pr_num and squash_match:
                pr_num = int(squash_match.group(1))

            # If no PR number pattern, but is a multi-file commit, synthesize a change unit
            if not pr_num:
                pr_num = pr_number_seq
                pr_number_seq += 1

            # Estimate created_at to be slightly before committed_at for lifecycle representation
            created_at = c.committed_at - timedelta(hours=max(1, (c.files_changed or 1)))

            prs.append(
                PullRequest(
                    github_node_id=f"git_{c.sha[:12]}",
                    number=pr_num,
                    repository_name_with_owner=repo_name,
                    repository_id=f"git_{repo_name}",
                    author_login=c.author_login,
                    author_type="Bot"
                    if (c.author_login and "[bot]" in c.author_login.lower())
                    else "User",
                    created_at=created_at,
                    closed_at=c.committed_at,
                    merged_at=c.committed_at,
                    state="MERGED",
                    is_draft=False,
                    additions=c.additions,
                    deletions=c.deletions,
                    changed_files=c.files_changed,
                    review_decision="APPROVED",
                    collected_at=collected_at,
                    ingestion_run_id=active_run_id,
                )
            )

        return prs

    def ingest_local_repository(
        self,
        path: Path,
        days: int | None = None,
        max_count: int | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute full local ingestion pipeline: parse, normalize, attribute, and persist."""
        if not self.is_git_repository(path):
            raise ValueError(f"Path '{path}' is not a valid git repository.")

        active_run_id = run_id or str(uuid.uuid4())
        repo_name = self.resolve_repository_name(path)
        safe_repo = repo_name.replace("/", "__")

        commits = self.extract_commits(path, days=days, max_count=max_count, run_id=active_run_id)
        prs = self.extract_pull_requests(path, commits=commits, run_id=active_run_id)

        # Detect AI attribution and synthesize developer telemetry
        telemetry = self.attribution_detector.synthesize_developer_telemetry(
            repository=repo_name, prs=prs, commits=commits
        )
        report = self.attribution_detector.analyze_repository(
            repository=repo_name, prs=prs, commits=commits
        )

        # Persist to canonical Parquet datasets
        self.settings.ensure_directories()
        pr_parquet = (
            self.settings.canonical_dir / f"pull_requests__{safe_repo}__{active_run_id}.parquet"
        )
        commit_parquet = (
            self.settings.canonical_dir / f"commits__{safe_repo}__{active_run_id}.parquet"
        )
        telemetry_parquet = self.settings.canonical_dir / f"ai_telemetry__{safe_repo}.parquet"

        write_canonical(prs, pr_parquet)
        write_canonical_commits(commits, commit_parquet)
        write_ai_telemetry(telemetry, telemetry_parquet)

        return {
            "run_id": active_run_id,
            "repository": repo_name,
            "total_commits": len(commits),
            "total_prs": len(prs),
            "ai_assisted_prs": report.ai_assisted_prs,
            "ai_penetration_rate": report.ai_penetration_rate,
            "detected_tools": [str(t.value) for t in report.detected_tools],
            "ai_active_developers": report.ai_active_developers,
            "canonical_pr_path": str(pr_parquet),
            "canonical_commit_path": str(commit_parquet),
            "canonical_telemetry_path": str(telemetry_parquet),
        }
