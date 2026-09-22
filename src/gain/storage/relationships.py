"""Columnar persistence and lookup for materialized cross-entity relationships."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl
import structlog

from gain.config import get_settings

log = structlog.get_logger(__name__)

RELATIONSHIP_SCHEMA = {
    "rel_type": pl.Utf8,
    "source_type": pl.Utf8,
    "source_id": pl.Utf8,
    "target_type": pl.Utf8,
    "target_id": pl.Utf8,
    "repository": pl.Utf8,
    "pr_number": pl.Int64,
    "issue_key": pl.Utf8,
    "commit_sha": pl.Utf8,
    "deployment_id": pl.Utf8,
    "metadata": pl.Utf8,
    "created_at": pl.Utf8,
}


class RelationshipStore:
    """Manages materialized cross-entity relationships backed by Parquet storage."""

    def __init__(self, storage_dir: Path | str | None = None) -> None:
        if storage_dir is not None:
            self.storage_dir = Path(storage_dir)
        else:
            settings = get_settings()
            idx_dir = settings.indexes_dir
            if idx_dir != Path("./data/indexes"):
                self.storage_dir = idx_dir
            elif settings.output_dir != Path("./data"):
                self.storage_dir = settings.output_dir / "indexes"
            else:
                self.storage_dir = idx_dir

        self.parquet_path = self.storage_dir / "relationships.parquet"

        # In-memory indexes for fast O(1) lookups
        self._pr_to_issues: dict[tuple[str, int], list[str]] = {}
        self._issue_to_prs: dict[str, list[dict[str, Any]]] = {}
        self._commit_to_deployments: dict[str, list[str]] = {}
        self._deployment_to_commits: dict[str, list[str]] = {}
        self._records: list[dict[str, Any]] = []

        self.load()

    def load(self) -> None:
        """Load materialized relationships from Parquet into memory."""
        if not self.parquet_path.exists():
            return

        try:
            df = pl.read_parquet(self.parquet_path)
            self._records = []
            self._pr_to_issues.clear()
            self._issue_to_prs.clear()
            self._commit_to_deployments.clear()
            self._deployment_to_commits.clear()

            for row in df.to_dicts():
                self._records.append(row)
                rel_type = row.get("rel_type")
                if rel_type == "pr_issue":
                    repo = row.get("repository")
                    pr_num = row.get("pr_number")
                    key = row.get("issue_key")
                    if repo and pr_num is not None and key:
                        self._index_pr_issue(str(repo), int(pr_num), str(key))
                elif rel_type == "commit_deployment":
                    sha = row.get("commit_sha")
                    dep_id = row.get("deployment_id")
                    if sha and dep_id:
                        self._index_commit_deployment(str(sha), str(dep_id))
        except Exception as exc:
            log.warning("relationships_load_failed", path=str(self.parquet_path), exc_info=exc)

    def _index_pr_issue(self, repo: str, pr_number: int, issue_key: str) -> None:
        key_pair = (repo, pr_number)
        if key_pair not in self._pr_to_issues:
            self._pr_to_issues[key_pair] = []
        if issue_key not in self._pr_to_issues[key_pair]:
            self._pr_to_issues[key_pair].append(issue_key)

        if issue_key not in self._issue_to_prs:
            self._issue_to_prs[issue_key] = []
        pr_ref = {"repository": repo, "pr_number": pr_number}
        if pr_ref not in self._issue_to_prs[issue_key]:
            self._issue_to_prs[issue_key].append(pr_ref)

    def _index_commit_deployment(self, sha: str, deployment_id: str) -> None:
        if sha not in self._commit_to_deployments:
            self._commit_to_deployments[sha] = []
        if deployment_id not in self._commit_to_deployments[sha]:
            self._commit_to_deployments[sha].append(deployment_id)

        if deployment_id not in self._deployment_to_commits:
            self._deployment_to_commits[deployment_id] = []
        if sha not in self._deployment_to_commits[deployment_id]:
            self._deployment_to_commits[deployment_id].append(sha)

    def save(self) -> None:
        """Atomically persist relationships to Parquet."""
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        df = pl.DataFrame(self._records, schema=RELATIONSHIP_SCHEMA)
        tmp_file = self.parquet_path.with_suffix(".tmp")
        try:
            df.write_parquet(tmp_file)
            tmp_file.replace(self.parquet_path)
        except Exception as exc:
            log.error("relationships_save_failed", path=str(self.parquet_path), exc_info=exc)
            if tmp_file.exists():
                tmp_file.unlink(missing_ok=True)
            raise

    def record_pr_issue_link(
        self,
        repository: str,
        pr_number: int,
        issue_key: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record a link between a pull request and a tracking issue."""
        repo = repository.strip()
        pr_num = int(pr_number)
        key = issue_key.strip()

        # Idempotency check
        existing_issues = self._pr_to_issues.get((repo, pr_num), [])
        if key in existing_issues:
            return

        self._index_pr_issue(repo, pr_num, key)

        row = {
            "rel_type": "pr_issue",
            "source_type": "pr",
            "source_id": f"{repo}#{pr_num}",
            "target_type": "issue",
            "target_id": key,
            "repository": repo,
            "pr_number": pr_num,
            "issue_key": key,
            "commit_sha": None,
            "deployment_id": None,
            "metadata": json.dumps(metadata) if metadata else None,
            "created_at": datetime.now(UTC).isoformat(),
        }
        self._records.append(row)
        self.save()

    def get_linked_issues(self, repository: str, pr_number: int) -> list[str]:
        """Return list of issue keys linked to the given PR."""
        repo = repository.strip()
        pr_num = int(pr_number)
        return list(self._pr_to_issues.get((repo, pr_num), []))

    def get_linked_prs(self, issue_key: str) -> list[dict[str, Any]]:
        """Return list of PR references (repository, pr_number) linked to the given issue."""
        key = issue_key.strip()
        return [dict(item) for item in self._issue_to_prs.get(key, [])]

    def record_commit_deployment_link(
        self,
        commit_sha: str,
        deployment_id: str,
        repository: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record a link between a commit SHA and a deployment event."""
        sha = commit_sha.strip()
        dep_id = deployment_id.strip()

        # Idempotency check
        existing_deps = self._commit_to_deployments.get(sha, [])
        if dep_id in existing_deps:
            return

        self._index_commit_deployment(sha, dep_id)

        row = {
            "rel_type": "commit_deployment",
            "source_type": "commit",
            "source_id": sha,
            "target_type": "deployment",
            "target_id": dep_id,
            "repository": repository.strip() if repository else None,
            "pr_number": None,
            "issue_key": None,
            "commit_sha": sha,
            "deployment_id": dep_id,
            "metadata": json.dumps(metadata) if metadata else None,
            "created_at": datetime.now(UTC).isoformat(),
        }
        self._records.append(row)
        self.save()

    def get_linked_deployments(self, commit_sha: str) -> list[str]:
        """Return deployment IDs linked to the given commit SHA."""
        return list(self._commit_to_deployments.get(commit_sha.strip(), []))

    def get_linked_commits(self, deployment_id: str) -> list[str]:
        """Return commit SHAs linked to the given deployment."""
        return list(self._deployment_to_commits.get(deployment_id.strip(), []))

    def as_dataframe(self) -> pl.DataFrame:
        """Return all relationships as a Polars DataFrame for join operations."""
        return pl.DataFrame(self._records, schema=RELATIONSHIP_SCHEMA)

    def clear(self) -> None:
        """Clear all in-memory relationships and delete the parquet file."""
        self._records.clear()
        self._pr_to_issues.clear()
        self._issue_to_prs.clear()
        self._commit_to_deployments.clear()
        self._deployment_to_commits.clear()
        if self.parquet_path.exists():
            self.parquet_path.unlink(missing_ok=True)
