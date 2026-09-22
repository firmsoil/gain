from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from gain.errors import RateLimitError
from gain.github.async_client import AsyncGitHubGraphQLClient
from gain.github.auth import PATAuth
from gain.github.token_pool import GitHubTokenPool
from gain.ingestion.queue import InProcessQueue, WorkItem
from gain.ingestion.worker import IngestionWorker
from gain.storage.checkpoint import CheckpointStore
from gain.storage.raw import RawStore


def _make_mock_page(
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


@pytest.mark.anyio
async def test_worker_process_item_multi_page(tmp_path: Path) -> None:
    raw_store = RawStore(tmp_path / "raw")
    checkpoint_store = CheckpointStore(tmp_path / "raw" / "checkpoints")

    node1 = {
        "id": "PR_1",
        "number": 1,
        "author": {"__typename": "User", "login": "dev1"},
        "createdAt": "2026-06-15T12:00:00Z",
        "closedAt": None,
        "mergedAt": None,
        "state": "OPEN",
        "isDraft": False,
    }
    node2 = {
        "id": "PR_2",
        "number": 2,
        "author": {"__typename": "User", "login": "dev2"},
        "createdAt": "2026-06-10T12:00:00Z",
        "closedAt": "2026-06-11T12:00:00Z",
        "mergedAt": "2026-06-11T12:00:00Z",
        "state": "CLOSED",
        "isDraft": False,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        after = body.get("variables", {}).get("after")
        if after is None:
            return httpx.Response(
                200, json=_make_mock_page([node1], has_next=True, end_cursor="cursor-1")
            )
        return httpx.Response(
            200, json=_make_mock_page([node2], has_next=False, end_cursor="cursor-2")
        )

    transport = httpx.MockTransport(handler)
    client = AsyncGitHubGraphQLClient(
        token="ghp_test",
        transport=transport,
        page_size=10,
    )

    worker = IngestionWorker(
        worker_id="test-worker",
        client=client,
        raw_store=raw_store,
        checkpoint_store=checkpoint_store,
        start_at=datetime(2026, 1, 1, tzinfo=UTC),
        end_at=datetime(2026, 12, 31, tzinfo=UTC),
    )

    item = WorkItem(repository="acme/repo1", run_id="run-001")
    result = await worker.process_item(item)

    assert result["repository"] == "acme/repo1"
    assert result["pages"] == 2
    assert result["nodes"] == 2
    assert result["completed"] is True

    # Checkpoint should be page 3, cursor-2
    chk = checkpoint_store.load("run-001", "acme/repo1")
    assert chk["next_page"] == 3
    assert chk["cursor"] == "cursor-2"

    # Raw store records
    records = raw_store.read_run("run-001")
    assert len(records) == 2

    # Verify telemetry metrics were recorded
    from gain.telemetry.metrics import INGESTION_NODES_TOTAL, INGESTION_PAGES_TOTAL

    assert INGESTION_PAGES_TOTAL.get(repository="acme/repo1", run_id="run-001") >= 2.0
    assert INGESTION_NODES_TOTAL.get(repository="acme/repo1", run_id="run-001") >= 2.0


@pytest.mark.anyio
async def test_worker_resumes_from_existing_checkpoint(tmp_path: Path) -> None:
    raw_store = RawStore(tmp_path / "raw")
    checkpoint_store = CheckpointStore(tmp_path / "raw" / "checkpoints")

    # Seed checkpoint with existing page 2
    checkpoint_store.save(
        "run-002",
        "acme/repo1",
        {"repository": "acme/repo1", "next_page": 2, "cursor": "existing-cursor"},
    )

    requested_cursors: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        after = body.get("variables", {}).get("after")
        requested_cursors.append(after)
        node = {
            "id": "PR_5",
            "number": 5,
            "author": {"__typename": "User", "login": "alice"},
            "createdAt": "2026-06-15T12:00:00Z",
            "closedAt": None,
            "mergedAt": None,
            "state": "OPEN",
            "isDraft": False,
        }
        return httpx.Response(
            200, json=_make_mock_page([node], has_next=False, end_cursor="cursor-final")
        )

    transport = httpx.MockTransport(handler)
    client = AsyncGitHubGraphQLClient(
        token="ghp_test",
        transport=transport,
    )

    worker = IngestionWorker(
        worker_id="worker-resume",
        client=client,
        raw_store=raw_store,
        checkpoint_store=checkpoint_store,
        start_at=datetime(2026, 1, 1, tzinfo=UTC),
        end_at=datetime(2026, 12, 31, tzinfo=UTC),
    )

    item = WorkItem(repository="acme/repo1", run_id="run-002")
    result = await worker.process_item(item)

    assert result["completed"] is True
    assert result["pages"] == 1
    assert requested_cursors == ["existing-cursor"]

    chk = checkpoint_store.load("run-002", "acme/repo1")
    assert chk["next_page"] == 3
    assert chk["cursor"] == "cursor-final"


@pytest.mark.anyio
async def test_worker_token_rotation_on_rate_limit(tmp_path: Path) -> None:
    raw_store = RawStore(tmp_path / "raw")
    checkpoint_store = CheckpointStore(tmp_path / "raw" / "checkpoints")

    token1 = PATAuth(token="ghp_token_one", name="pat-1")
    token2 = PATAuth(token="ghp_token_two", name="pat-2")
    token_pool = GitHubTokenPool([token1, token2])

    auth_headers_seen: list[str] = []

    node1 = {
        "id": "PR_100",
        "number": 100,
        "author": {"__typename": "User", "login": "dev"},
        "createdAt": "2026-06-15T12:00:00Z",
        "closedAt": None,
        "mergedAt": None,
        "state": "OPEN",
        "isDraft": False,
    }
    node2 = {
        "id": "PR_101",
        "number": 101,
        "author": {"__typename": "User", "login": "dev"},
        "createdAt": "2026-06-14T12:00:00Z",
        "closedAt": None,
        "mergedAt": None,
        "state": "OPEN",
        "isDraft": False,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        auth_header = request.headers.get("authorization", "")
        auth_headers_seen.append(auth_header)
        body = json.loads(request.content.decode("utf-8"))
        after = body.get("variables", {}).get("after")

        if auth_header == "Bearer ghp_token_one":
            if after is None:
                # Page 1 succeeds
                return httpx.Response(
                    200, json=_make_mock_page([node1], has_next=True, end_cursor="cur-1")
                )
            # Page 2 fails with 429
            return httpx.Response(
                429,
                headers={"retry-after": "60", "x-ratelimit-reset": "9999999999"},
                json={"message": "API rate limit exceeded"},
            )
        elif auth_header == "Bearer ghp_token_two":
            # Token 2 gets page 2 successfully
            return httpx.Response(
                200, json=_make_mock_page([node2], has_next=False, end_cursor="cur-2")
            )
        return httpx.Response(401, json={"message": "Bad credentials"})

    transport = httpx.MockTransport(handler)

    worker = IngestionWorker(
        worker_id="rotating-worker",
        token_pool=token_pool,
        raw_store=raw_store,
        checkpoint_store=checkpoint_store,
        start_at=datetime(2026, 1, 1, tzinfo=UTC),
        end_at=datetime(2026, 12, 31, tzinfo=UTC),
        max_retries=0,
        base_backoff_seconds=0.001,
        transport=transport,
    )

    item = WorkItem(repository="acme/repo1", run_id="run-rotation")
    result = await worker.process_item(item)

    assert result["completed"] is True
    assert result["pages"] == 2
    assert result["nodes"] == 2

    # Verify token 1 was exhausted and token 2 was used
    assert token1.is_exhausted() is True
    assert any("ghp_token_two" in h for h in auth_headers_seen)

    chk = checkpoint_store.load("run-rotation", "acme/repo1")
    assert chk["next_page"] == 3
    assert chk["cursor"] == "cur-2"


@pytest.mark.anyio
async def test_worker_all_tokens_exhausted_raises(tmp_path: Path) -> None:
    raw_store = RawStore(tmp_path / "raw")
    checkpoint_store = CheckpointStore(tmp_path / "raw" / "checkpoints")

    token1 = PATAuth(token="ghp_only_one", name="pat-solo")
    token_pool = GitHubTokenPool([token1])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            headers={"retry-after": "60"},
            json={"message": "API rate limit exceeded"},
        )

    transport = httpx.MockTransport(handler)
    worker = IngestionWorker(
        worker_id="exhausted-worker",
        token_pool=token_pool,
        raw_store=raw_store,
        checkpoint_store=checkpoint_store,
        start_at=datetime(2026, 1, 1, tzinfo=UTC),
        end_at=datetime(2026, 12, 31, tzinfo=UTC),
        max_retries=0,
        base_backoff_seconds=0.001,
        transport=transport,
    )

    item = WorkItem(repository="acme/repo1", run_id="run-exhausted")
    with pytest.raises(RateLimitError):
        await worker.process_item(item)


@pytest.mark.anyio
async def test_worker_in_window_filtering(tmp_path: Path) -> None:
    raw_store = RawStore(tmp_path / "raw")
    checkpoint_store = CheckpointStore(tmp_path / "raw" / "checkpoints")

    # Nodes: 1 before window, 1 in window, 1 after window
    node_before = {
        "id": "PR_BEFORE",
        "number": 1,
        "createdAt": "2025-12-31T23:59:59Z",
        "state": "OPEN",
    }
    node_in = {
        "id": "PR_IN",
        "number": 2,
        "createdAt": "2026-06-15T12:00:00Z",
        "state": "OPEN",
    }
    node_after = {
        "id": "PR_AFTER",
        "number": 3,
        "createdAt": "2027-01-01T00:00:01Z",
        "state": "OPEN",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_make_mock_page(
                [node_after, node_in, node_before], has_next=False, end_cursor="cur-0"
            ),
        )

    transport = httpx.MockTransport(handler)
    client = AsyncGitHubGraphQLClient(token="ghp_test", transport=transport)

    worker = IngestionWorker(
        worker_id="filter-worker",
        client=client,
        raw_store=raw_store,
        checkpoint_store=checkpoint_store,
        start_at=datetime(2026, 1, 1, tzinfo=UTC),
        end_at=datetime(2026, 12, 31, tzinfo=UTC),
    )

    item = WorkItem(repository="acme/repo1", run_id="run-filter")
    result = await worker.process_item(item)

    assert result["pages"] == 1
    assert result["nodes"] == 1  # Only 1 node in window!

    records = raw_store.read_run("run-filter")
    assert len(records) == 1
    assert records[0]["node"]["id"] == "PR_IN"


@pytest.mark.anyio
async def test_worker_run_loop_drains_queue(tmp_path: Path) -> None:
    raw_store = RawStore(tmp_path / "raw")
    checkpoint_store = CheckpointStore(tmp_path / "raw" / "checkpoints")

    def handler(request: httpx.Request) -> httpx.Response:
        node = {
            "id": "PR_GENERIC",
            "number": 10,
            "createdAt": "2026-06-15T12:00:00Z",
            "state": "OPEN",
        }
        return httpx.Response(200, json=_make_mock_page([node], has_next=False))

    transport = httpx.MockTransport(handler)
    client = AsyncGitHubGraphQLClient(token="ghp_test", transport=transport)

    worker = IngestionWorker(
        worker_id="loop-worker",
        client=client,
        raw_store=raw_store,
        checkpoint_store=checkpoint_store,
        start_at=datetime(2026, 1, 1, tzinfo=UTC),
        end_at=datetime(2026, 12, 31, tzinfo=UTC),
    )

    queue = InProcessQueue(
        [
            WorkItem(repository="acme/repo-a", run_id="run-queue"),
            WorkItem(repository="acme/repo-b", run_id="run-queue"),
        ]
    )

    summary = await worker.run(queue)
    assert summary["repositories_processed"] == 2
    assert summary["pages_fetched"] == 2
    assert summary["nodes_captured"] == 2
    assert queue.qsize() == 0
    assert len(queue.completed) == 2
