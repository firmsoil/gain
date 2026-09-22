from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from gain.config import Settings
from gain.github.async_client import AsyncGitHubGraphQLClient
from gain.github.client import GitHubGraphQLClient
from gain.ingestion.coordinator import IngestionCoordinator
from gain.ingestion.queue import WorkItem
from gain.ingestion.worker import IngestionWorker
from gain.storage.checkpoint import CheckpointStore
from gain.storage.raw import RawStore
from gain.sync import PullRequestBackfill


def _make_page(
    nodes: list[dict[str, Any]],
    has_next: bool = False,
    end_cursor: str | None = None,
    repo_name: str = "acme/repo1",
) -> dict[str, Any]:
    return {
        "data": {
            "repository": {
                "id": "R_001",
                "nameWithOwner": repo_name,
                "pullRequests": {
                    "nodes": nodes,
                    "pageInfo": {
                        "hasNextPage": has_next,
                        "endCursor": end_cursor,
                    },
                },
            }
        }
    }


def test_pull_request_backfill_shutdown_requested(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    checkpoint_store = CheckpointStore(raw_dir / "checkpoints")

    page1_node = {
        "id": "PR_1",
        "number": 1,
        "createdAt": "2026-06-15T12:00:00Z",
        "state": "OPEN",
    }
    page2_node = {
        "id": "PR_2",
        "number": 2,
        "createdAt": "2026-06-14T12:00:00Z",
        "state": "OPEN",
    }

    fetch_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal fetch_count
        fetch_count += 1
        body = json.loads(request.content.decode("utf-8"))
        after = body.get("variables", {}).get("after")
        if after is None:
            return httpx.Response(
                200, json=_make_page([page1_node], has_next=True, end_cursor="cur-1")
            )
        return httpx.Response(
            200, json=_make_page([page2_node], has_next=False, end_cursor="cur-2")
        )

    transport = httpx.MockTransport(handler)
    client = GitHubGraphQLClient(token="ghp_test", transport=transport)

    settings = Settings(
        github_repos=["acme/repo1"],
        github_token="ghp_test",
        start_at=datetime(2026, 1, 1, tzinfo=UTC),
        end_at=datetime(2026, 12, 31, tzinfo=UTC),
        raw_dir=raw_dir,
        output_dir=tmp_path / "output",
    )

    backfill = PullRequestBackfill(settings, client)

    # Monkey-patch raw_store.append_page to trigger request_shutdown during first page
    orig_append_page = backfill.raw.append_page

    def append_page_and_shutdown(**kwargs: Any) -> Path:
        res = orig_append_page(**kwargs)
        backfill.request_shutdown()
        return res

    backfill.raw.append_page = append_page_and_shutdown  # type: ignore[method-assign]

    totals = backfill.run(ingestion_run_id="run-sync-shutdown")

    assert totals["shutdown_requested"] is True
    assert totals["pages"] == 1
    assert totals["nodes"] == 1
    # Second page should not have been fetched
    assert fetch_count == 1

    # Checkpoint was saved after page 1
    chk = checkpoint_store.load("run-sync-shutdown", "acme/repo1")
    assert chk["next_page"] == 2
    assert chk["cursor"] == "cur-1"


@pytest.mark.anyio
async def test_async_worker_graceful_shutdown_preserves_checkpoint(tmp_path: Path) -> None:
    raw_store = RawStore(tmp_path / "raw")
    checkpoint_store = CheckpointStore(tmp_path / "raw" / "checkpoints")

    page1_node = {
        "id": "PR_P1",
        "number": 1,
        "createdAt": "2026-06-15T12:00:00Z",
        "state": "OPEN",
    }
    page2_node = {
        "id": "PR_P2",
        "number": 2,
        "createdAt": "2026-06-14T12:00:00Z",
        "state": "OPEN",
    }
    page3_node = {
        "id": "PR_P3",
        "number": 3,
        "createdAt": "2026-06-13T12:00:00Z",
        "state": "OPEN",
    }

    fetch_log: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        after = body.get("variables", {}).get("after")
        fetch_log.append(after)
        if after is None:
            return httpx.Response(
                200, json=_make_page([page1_node], has_next=True, end_cursor="cur-p1")
            )
        elif after == "cur-p1":
            return httpx.Response(
                200, json=_make_page([page2_node], has_next=True, end_cursor="cur-p2")
            )
        return httpx.Response(
            200, json=_make_page([page3_node], has_next=False, end_cursor="cur-p3")
        )

    transport = httpx.MockTransport(handler)
    client = AsyncGitHubGraphQLClient(token="ghp_test", transport=transport)

    worker = IngestionWorker(
        worker_id="shutdown-worker",
        client=client,
        raw_store=raw_store,
        checkpoint_store=checkpoint_store,
        start_at=datetime(2026, 1, 1, tzinfo=UTC),
        end_at=datetime(2026, 12, 31, tzinfo=UTC),
    )

    # Trigger shutdown when page 1 is appended
    orig_append = raw_store.append_page

    def append_and_signal(**kwargs: Any) -> Path:
        p = orig_append(**kwargs)
        worker.request_shutdown()
        return p

    raw_store.append_page = append_and_signal  # type: ignore[method-assign]

    item = WorkItem(repository="acme/repo1", run_id="run-worker-shutdown")
    res = await worker.process_item(item)

    assert res["completed"] is False
    assert res["pages"] == 1
    assert res["nodes"] == 1

    # Checkpoint must be saved for page 1
    chk = checkpoint_store.load("run-worker-shutdown", "acme/repo1")
    assert chk["next_page"] == 2
    assert chk["cursor"] == "cur-p1"

    # Now simulate resume: restore original append_page and create new worker
    raw_store.append_page = orig_append  # type: ignore[method-assign]
    resume_worker = IngestionWorker(
        worker_id="resume-worker",
        client=client,
        raw_store=raw_store,
        checkpoint_store=checkpoint_store,
        start_at=datetime(2026, 1, 1, tzinfo=UTC),
        end_at=datetime(2026, 12, 31, tzinfo=UTC),
    )

    resume_res = await resume_worker.process_item(item)
    assert resume_res["completed"] is True
    assert resume_res["pages"] == 2
    assert resume_res["nodes"] == 2

    final_chk = checkpoint_store.load("run-worker-shutdown", "acme/repo1")
    assert final_chk["next_page"] == 4
    assert final_chk["cursor"] == "cur-p3"

    # Raw store contains all 3 distinct pages
    records = raw_store.read_run("run-worker-shutdown")
    assert len(records) == 3
    ids = [r["node"]["id"] for r in records]
    assert ids == ["PR_P1", "PR_P2", "PR_P3"]


@pytest.mark.anyio
async def test_coordinator_graceful_shutdown(tmp_path: Path) -> None:
    raw_store = RawStore(tmp_path / "raw")
    checkpoint_store = CheckpointStore(tmp_path / "checkpoints")

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        variables = body.get("variables", {})
        owner = variables.get("owner", "acme")
        name = variables.get("name", "repo-1")
        full_repo = f"{owner}/{name}"
        return httpx.Response(
            200,
            json=_make_page(
                [{"id": f"PR_{name}_1", "number": 1, "createdAt": "2026-06-15T12:00:00Z"}],
                has_next=False,
                repo_name=full_repo,
            ),
        )

    transport = httpx.MockTransport(handler)
    client = AsyncGitHubGraphQLClient(token="ghp_test", transport=transport)

    settings = Settings(
        github_repos=["acme/r1", "acme/r2", "acme/r3", "acme/r4"],
        github_token="ghp_test",
        start_at=datetime(2026, 1, 1, tzinfo=UTC),
        end_at=datetime(2026, 12, 31, tzinfo=UTC),
        raw_dir=tmp_path / "raw",
        output_dir=tmp_path / "output",
    )

    coordinator = IngestionCoordinator(
        settings=settings,
        client=client,
        num_workers=2,
        raw_store=raw_store,
        checkpoint_store=checkpoint_store,
        transport=transport,
    )

    # Intercept append_page to trigger shutdown after first repo page is appended
    orig_append = raw_store.append_page

    def append_and_shutdown_coord(**kwargs: Any) -> Path:
        p = orig_append(**kwargs)
        coordinator.request_shutdown()
        return p

    raw_store.append_page = append_and_shutdown_coord  # type: ignore[method-assign]

    totals = await coordinator.run(run_id="run-coord-shutdown")
    assert totals["shutdown_requested"] is True
    # At least 1 page and node was captured and checkpointed before shutdown
    assert totals["pages_fetched"] >= 1
    assert totals["nodes_captured"] >= 1
    assert totals["failures"] == 0

    chk = checkpoint_store.load("run-coord-shutdown", "acme/r1")
    assert chk["next_page"] == 2
