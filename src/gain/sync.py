from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog

from gain.config import Settings
from gain.github.client import GitHubGraphQLClient
from gain.storage.checkpoint import CheckpointStore
from gain.storage.raw import RawStore

log = structlog.get_logger(__name__)


class PullRequestBackfill:
    def __init__(self, settings: Settings, client: GitHubGraphQLClient) -> None:
        self.settings = settings
        self.client = client
        self.raw = RawStore(settings.raw_dir)
        self.checkpoints = CheckpointStore(settings.raw_dir / "checkpoints")

    def run(self, ingestion_run_id: str | None = None) -> dict[str, Any]:
        self.settings.ensure_directories()
        run_id = ingestion_run_id or str(uuid.uuid4())
        totals: dict[str, Any] = {
            "run_id": run_id,
            "repositories": 0,
            "pages": 0,
            "nodes": 0,
            "started_at": datetime.now(UTC).isoformat(),
        }
        for repository in self.settings.github_repos:
            owner, name = repository.split("/", 1)
            checkpoint = self.checkpoints.load(run_id, repository)
            page_number = int(checkpoint["next_page"])
            cursor = checkpoint.get("cursor")
            log.info("backfill_repository_start", repository=repository, page=page_number)
            for page in self.client.iter_pull_request_pages(
                owner,
                name,
                self.settings.start_at,
                self.settings.end_at,
                start_cursor=cursor,
            ):
                relevant = [node for node in page.nodes if self._in_window(node)]
                self.raw.append_page(
                    ingestion_run_id=run_id,
                    owner=owner,
                    name=name,
                    page_number=page_number,
                    cursor=cursor,
                    repository_id=page.repository_id,
                    repository_name_with_owner=page.repository_name_with_owner,
                    nodes=relevant,
                )
                totals["pages"] = int(totals["pages"]) + 1
                totals["nodes"] = int(totals["nodes"]) + len(relevant)
                next_page = page_number + 1
                self.checkpoints.save(
                    run_id,
                    repository,
                    {"repository": repository, "next_page": next_page, "cursor": page.end_cursor},
                )
                page_number = next_page
                cursor = page.end_cursor
            totals["repositories"] = int(totals["repositories"]) + 1
        totals["completed_at"] = datetime.now(UTC).isoformat()
        return totals

    def _in_window(self, node: dict[str, Any]) -> bool:
        created_raw = node.get("createdAt")
        if not isinstance(created_raw, str):
            return False
        created = _parse_datetime(created_raw)
        return self.settings.start_at <= created <= self.settings.end_at


def _parse_datetime(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)
