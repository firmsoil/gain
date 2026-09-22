from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from gain.cli import app
from gain.config import Settings
from gain.github.async_client import AsyncGitHubGraphQLClient
from gain.ingestion.coordinator import IngestionCoordinator
from gain.ingestion.queue import InProcessQueue
from gain.registry import RepoEntry, RepositoryRegistry
from gain.storage.checkpoint import CheckpointStore
from gain.storage.raw import RawStore

runner = CliRunner()


def _make_mock_page(
    repo_name: str,
    nodes: list[dict[str, Any]] | None = None,
    has_next: bool = False,
    end_cursor: str | None = None,
) -> dict[str, Any]:
    default_nodes = [
        {
            "id": f"PR_{repo_name.replace('/', '_')}_1",
            "number": 1,
            "author": {"__typename": "User", "login": "alice"},
            "createdAt": "2026-06-15T12:00:00Z",
            "closedAt": None,
            "mergedAt": None,
            "state": "OPEN",
            "isDraft": False,
        }
    ]
    return {
        "data": {
            "repository": {
                "id": f"R_{repo_name.replace('/', '_')}",
                "nameWithOwner": repo_name,
                "pullRequests": {
                    "nodes": nodes if nodes is not None else default_nodes,
                    "pageInfo": {
                        "hasNextPage": has_next,
                        "endCursor": end_cursor,
                    },
                },
            }
        }
    }


def test_coordinator_target_repos_from_registry_with_tier(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.parquet"
    registry = RepositoryRegistry(registry_path)
    registry.add_batch(
        [
            RepoEntry(name_with_owner="acme/critical-repo", org_id="acme", tier="critical"),
            RepoEntry(name_with_owner="acme/standard-repo", org_id="acme", tier="standard"),
            RepoEntry(name_with_owner="acme/archive-repo", org_id="acme", tier="archive"),
            RepoEntry(
                name_with_owner="acme/old-repo",
                org_id="acme",
                tier="critical",
                is_archived=True,
            ),
        ]
    )

    coordinator = IngestionCoordinator(
        registry=registry,
        tier="critical",
        raw_store=RawStore(tmp_path / "raw"),
        checkpoint_store=CheckpointStore(tmp_path / "checkpoints"),
    )

    repos = coordinator.get_target_repositories()
    assert repos == [("acme/critical-repo", "critical")]


def test_coordinator_target_repos_fallback_to_settings(tmp_path: Path) -> None:
    settings = Settings(
        github_repos=["org1/repo1", "org2/repo2"],
        github_token="ghp_test",
        start_at=datetime(2026, 1, 1, tzinfo=UTC),
        end_at=datetime(2026, 12, 31, tzinfo=UTC),
        raw_dir=tmp_path / "raw",
        output_dir=tmp_path / "output",
    )

    coordinator = IngestionCoordinator(
        settings=settings,
        tier="standard",
        raw_store=RawStore(tmp_path / "raw"),
        checkpoint_store=CheckpointStore(tmp_path / "checkpoints"),
    )

    repos = coordinator.get_target_repositories()
    assert repos == [("org1/repo1", "standard"), ("org2/repo2", "standard")]


@pytest.mark.anyio
async def test_coordinator_fan_out_multiple_workers_and_draining(tmp_path: Path) -> None:
    raw_store = RawStore(tmp_path / "raw")
    checkpoint_store = CheckpointStore(tmp_path / "checkpoints")

    repo_names = [f"acme/repo-{i}" for i in range(1, 7)]

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        variables = body.get("variables", {})
        owner = variables.get("owner", "acme")
        name = variables.get("name", "repo-1")
        full_repo = f"{owner}/{name}"
        return httpx.Response(200, json=_make_mock_page(full_repo))

    transport = httpx.MockTransport(handler)

    client = AsyncGitHubGraphQLClient(
        token="ghp_test",
        transport=transport,
    )

    settings = Settings(
        github_repos=repo_names,
        github_token="ghp_test",
        start_at=datetime(2026, 1, 1, tzinfo=UTC),
        end_at=datetime(2026, 12, 31, tzinfo=UTC),
        raw_dir=tmp_path / "raw",
        output_dir=tmp_path / "output",
    )

    coordinator = IngestionCoordinator(
        settings=settings,
        client=client,
        num_workers=3,
        batch_size=25,
        raw_store=raw_store,
        checkpoint_store=checkpoint_store,
        transport=transport,
    )

    totals = await coordinator.run(run_id="run-fanout-001")

    assert totals["run_id"] == "run-fanout-001"
    assert totals["repositories_processed"] == 6
    assert totals["pages_fetched"] == 6
    assert totals["nodes_captured"] == 6
    assert totals["failures"] == 0
    assert totals["duration_seconds"] >= 0.0

    # Queue should be completely drained
    assert coordinator.queue.qsize() == 0
    if isinstance(coordinator.queue, InProcessQueue):
        assert len(coordinator.queue.completed) == 6
        assert len(coordinator.queue.failed) == 0

    # Checkpoint store should have checkpoints for all 6 repositories
    checkpoints = checkpoint_store.list_checkpoints("run-fanout-001")
    assert len(checkpoints) == 6
    for repo in repo_names:
        assert repo in checkpoints
        assert checkpoints[repo]["next_page"] == 2


@pytest.mark.anyio
async def test_coordinator_failure_handling_and_retry(tmp_path: Path) -> None:
    raw_store = RawStore(tmp_path / "raw")
    checkpoint_store = CheckpointStore(tmp_path / "checkpoints")

    repo_names = ["acme/good1", "acme/failing-repo", "acme/good2"]

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        variables = body.get("variables", {})
        name = variables.get("name", "")
        if name == "failing-repo":
            # Return HTTP 500 error
            return httpx.Response(500, json={"message": "Internal Server Error"})
        return httpx.Response(200, json=_make_mock_page(f"acme/{name}"))

    transport = httpx.MockTransport(handler)

    client = AsyncGitHubGraphQLClient(
        token="ghp_test",
        transport=transport,
        max_retries=0,
    )

    settings = Settings(
        github_repos=repo_names,
        github_token="ghp_test",
        start_at=datetime(2026, 1, 1, tzinfo=UTC),
        end_at=datetime(2026, 12, 31, tzinfo=UTC),
        raw_dir=tmp_path / "raw",
        output_dir=tmp_path / "output",
        max_retries=0,
    )

    coordinator = IngestionCoordinator(
        settings=settings,
        client=client,
        num_workers=2,
        raw_store=raw_store,
        checkpoint_store=checkpoint_store,
        transport=transport,
    )

    totals = await coordinator.run(run_id="run-failure-001")

    # 2 repositories should succeed, 1 should fail
    assert totals["repositories_processed"] == 2
    assert totals["failures"] == 1
    assert totals["pages_fetched"] == 2
    assert totals["nodes_captured"] == 2

    if isinstance(coordinator.queue, InProcessQueue):
        assert len(coordinator.queue.completed) == 2
        assert len(coordinator.queue.failed) == 1
        failed_item, error = coordinator.queue.failed[0]
        assert failed_item.repository == "acme/failing-repo"
        assert "500" in error


def test_cli_gain_sync_help() -> None:
    result = runner.invoke(app, ["sync", "--help"])
    assert result.exit_code == 0
    assert "--workers" in result.stdout
    assert "-w" in result.stdout
    assert "--batch-size" in result.stdout
    assert "-b" in result.stdout
    assert "--tier" in result.stdout
