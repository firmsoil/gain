from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx

from gain.config import Settings
from gain.github.client import GitHubGraphQLClient
from gain.storage.checkpoint import CheckpointStore
from gain.storage.raw import RawStore
from gain.sync import PullRequestBackfill


def test_checkpoint_store_lifecycle(tmp_path: Path) -> None:
    store = CheckpointStore(tmp_path / "checkpoints")
    run_id = "run-chk-001"
    repo = "acme/example"

    # Default checkpoint on missing file
    initial = store.load(run_id, repo)
    assert initial["repository"] == repo
    assert initial["next_page"] == 1
    assert initial["cursor"] is None

    # Save state
    store.save(run_id, repo, {"repository": repo, "next_page": 2, "cursor": "cur-123"})
    loaded = store.load(run_id, repo)
    assert loaded["next_page"] == 2
    assert loaded["cursor"] == "cur-123"


def test_pull_request_backfill_run(tmp_path: Path) -> None:
    # Build two mock pages of GraphQL responses
    page1 = {
        "data": {
            "repository": {
                "id": "R_1",
                "nameWithOwner": "acme/repo1",
                "pullRequests": {
                    "nodes": [
                        {
                            "id": "PR_10",
                            "number": 10,
                            "author": {"__typename": "User", "login": "dev1"},
                            "createdAt": "2026-01-15T12:00:00Z",
                            "closedAt": "2026-01-15T18:00:00Z",
                            "mergedAt": "2026-01-15T18:00:00Z",
                            "state": "CLOSED",
                            "isDraft": False,
                        }
                    ],
                    "pageInfo": {"hasNextPage": True, "endCursor": "cursor-p1"},
                },
            }
        }
    }
    page2 = {
        "data": {
            "repository": {
                "id": "R_1",
                "nameWithOwner": "acme/repo1",
                "pullRequests": {
                    "nodes": [
                        {
                            "id": "PR_9",
                            "number": 9,
                            "author": {"__typename": "User", "login": "dev2"},
                            "createdAt": "2026-01-10T12:00:00Z",
                            "closedAt": None,
                            "mergedAt": None,
                            "state": "OPEN",
                            "isDraft": False,
                        }
                    ],
                    "pageInfo": {"hasNextPage": False, "endCursor": "cursor-p2"},
                },
            }
        }
    }

    call_count = 0

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        body = json.loads(request.content.decode("utf-8"))
        after_cursor = body.get("variables", {}).get("after")
        if after_cursor is None:
            return httpx.Response(200, json=page1)
        return httpx.Response(200, json=page2)

    settings = Settings(
        github_token="ghp_mock_token",
        github_repos=["acme/repo1"],
        start_at=datetime(2026, 1, 1, tzinfo=UTC),
        end_at=datetime(2026, 1, 31, tzinfo=UTC),
        raw_dir=tmp_path / "raw",
        output_dir=tmp_path / "output",
        canonical_dir=tmp_path / "canonical",
        metrics_dir=tmp_path / "metrics",
    )

    client = GitHubGraphQLClient(
        token="ghp_mock_token",
        transport=httpx.MockTransport(mock_handler),
        jitter=False,
    )

    backfill = PullRequestBackfill(settings, client)
    run_id = "test-backfill-run-123"
    result = backfill.run(ingestion_run_id=run_id)

    assert result["run_id"] == run_id
    assert result["repositories"] == 1
    assert result["pages"] == 2
    assert result["nodes"] == 2

    raw_records = RawStore(tmp_path / "raw").read_run(run_id)
    assert len(raw_records) == 2
    assert raw_records[0]["node"]["id"] == "PR_10"
    assert raw_records[1]["node"]["id"] == "PR_9"

    # Checkpoint should record next_page=3 and cursor-p2
    checkpoint = CheckpointStore(tmp_path / "raw" / "checkpoints").load(run_id, "acme/repo1")
    assert checkpoint["next_page"] == 3
    assert checkpoint["cursor"] == "cursor-p2"
