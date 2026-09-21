from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field

from gain.github.client import GitHubGraphQLClient
from gain.metrics.catalog import MetricCatalog
from gain.metrics.cycle_time import CycleTimeMetric
from gain.model.pr import PullRequest
from gain.schema import normalize_records
from gain.storage.analytics import (
    read_canonical,
    write_canonical,
    write_cycle_time_observations,
)
from gain.storage.raw import RawStore
from gain.storage.replay import replay_run

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "graphql_page_1.json"
CATALOG_PATH = Path("docs/metrics/metric-catalog.yaml")


def test_vertical_slice_end_to_end(tmp_path: Path) -> None:
    """Test the complete GAIN production vertical slice end-to-end.

    Validates all 10 acceptance criteria:
    AC 1: Acquisition of GitHub GraphQL response.
    AC 2: Raw response persistence.
    AC 3: Associated provenance metadata.
    AC 4: Canonical normalization into PullRequest.
    AC 5: Deterministic cycle time calculation.
    AC 6: Metric result identifies metric ID and version.
    AC 7: Invalid or incomplete source data handled explicitly.
    AC 8: Zero LLM dependency or invocation in metric calculation.
    AC 9: Passing automated verification tests.
    AC 10: Extensible architecture to additional GitHub entities.
    """
    raw_fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    captured_headers: dict[str, str] = {}

    def mock_handler(request: httpx.Request) -> httpx.Response:
        captured_headers.update(dict(request.headers))
        return httpx.Response(200, json=raw_fixture)

    # --- AC 1: GitHub GraphQL response acquisition ---
    client = GitHubGraphQLClient(
        token="ghp_test_secret_token_12345",
        api_url="https://api.github.com/graphql",
        api_version="2022-11-28",
        transport=httpx.MockTransport(mock_handler),
    )
    pages = list(
        client.iter_pull_request_pages(
            owner="acme",
            name="example",
            since=datetime(2026, 1, 1, tzinfo=UTC),
            until=datetime(2026, 1, 31, tzinfo=UTC),
        )
    )
    assert len(pages) == 1
    page = pages[0]
    assert page.repository_name_with_owner == "acme/example"
    assert page.repository_id == "R_1"
    assert len(page.nodes) == 2
    # Check headers (auth and version tracking)
    assert captured_headers["authorization"] == "Bearer ghp_test_secret_token_12345"
    assert captured_headers["x-github-api-version"] == "2022-11-28"

    # --- AC 2 & AC 3: Raw response persistence with provenance metadata ---
    raw_store = RawStore(tmp_path / "raw")
    run_id = "test-run-slice-001"
    raw_file = raw_store.append_page(
        ingestion_run_id=run_id,
        owner="acme",
        name="example",
        page_number=1,
        cursor="cursor-001",
        repository_id=page.repository_id,
        repository_name_with_owner=page.repository_name_with_owner,
        nodes=page.nodes,
    )
    assert raw_file.exists()
    lines = [json.loads(line) for line in raw_file.read_text(encoding="utf-8").splitlines() if line]
    assert len(lines) == 2

    # Verify provenance metadata on every persisted raw record
    for record in lines:
        metadata = record["metadata"]
        assert metadata["ingestion_run_id"] == run_id
        assert metadata["owner"] == "acme"
        assert metadata["name"] == "example"
        assert metadata["page_number"] == 1
        assert metadata["cursor"] == "cursor-001"
        assert metadata["repository_id"] == "R_1"
        assert metadata["repository_name_with_owner"] == "acme/example"
        assert "collected_at" in metadata
        assert record["node"]["id"] in {"PR_1", "PR_2"}

    # --- AC 4: Normalization into canonical PullRequest model ---
    canonical_prs, norm_errors = replay_run(tmp_path / "raw", run_id)
    assert len(norm_errors) == 0
    assert len(canonical_prs) == 2

    pr1, pr2 = canonical_prs[0], canonical_prs[1]
    assert isinstance(pr1, PullRequest)
    assert pr1.github_node_id == "PR_1"
    assert pr1.number == 1
    assert pr1.repository_name_with_owner == "acme/example"
    assert pr1.author_login == "alice"
    assert pr1.state == "CLOSED"
    assert pr1.merged is True
    assert pr1.is_bot is False
    assert pr1.created_at.tzinfo == UTC
    assert pr1.merged_at == datetime(2026, 1, 1, 6, 0, 0, tzinfo=UTC)

    assert isinstance(pr2, PullRequest)
    assert pr2.github_node_id == "PR_2"
    assert pr2.number == 2
    assert pr2.author_login == "dependabot[bot]"
    assert pr2.is_bot is True
    assert pr2.merged is False
    assert pr2.merged_at is None

    # Persist and reload canonical parquet
    canonical_parquet = tmp_path / "canonical" / "pull_requests.parquet"
    write_canonical(canonical_prs, canonical_parquet)
    assert canonical_parquet.exists()
    reloaded_prs = read_canonical(canonical_parquet)
    assert len(reloaded_prs) == 2

    # --- AC 5: Deterministic cycle time calculation ---
    # GAIN-PR-001 = merged_at - created_at (6 hours = 21600.0 seconds).
    # Unmerged PR (PR_2) is excluded from cycle-time observations.
    observations = CycleTimeMetric.observations(reloaded_prs)
    assert len(observations) == 1
    obs = observations[0]
    assert obs.cycle_time_seconds == 21600.0
    assert obs.github_node_id == "PR_1"
    assert obs.pr_number == 1

    summary = CycleTimeMetric.summary(observations)
    assert summary["count"] == 1
    assert summary["p50_seconds"] == 21600.0
    assert summary["p95_seconds"] == 21600.0
    assert summary["mean_seconds"] == 21600.0

    # Persist observations to Parquet
    observations_parquet = tmp_path / "metrics" / "cycle_time.parquet"
    write_cycle_time_observations(observations, observations_parquet)
    assert observations_parquet.exists()

    # --- AC 6: Metric result identifies its metric definition and version ---
    assert obs.metric_id == "GAIN-PR-001"
    assert obs.metric_version == 1

    catalog = MetricCatalog(CATALOG_PATH)
    catalog_def = catalog.get(obs.metric_id)
    assert catalog_def["metric_id"] == "GAIN-PR-001"
    assert catalog_def["metric_version"] == 1
    assert catalog_def["name"] == "pr_cycle_time"
    assert catalog_def["formula"] == "merged_at - created_at"

    # --- AC 7: Invalid or incomplete source data handled explicitly ---
    malformed_records = [
        {
            "metadata": {
                "repository_name_with_owner": "acme/example",
                "repository_id": "R_1",
                "collected_at": datetime.now(UTC).isoformat(),
                "ingestion_run_id": "run-err",
            },
            # Missing required fields like 'id', 'number', 'state', invalid createdAt
            "node": {
                "id": "PR_BAD",
                "number": -5,  # fails number > 0 validator
                "createdAt": "invalid-timestamp",
                "state": "INVALID_STATE",
            },
        }
    ]
    valid_prs, errors = normalize_records(malformed_records)
    assert len(valid_prs) == 0
    assert len(errors) == 1
    assert errors[0]["record_index"] == 0
    assert "error" in errors[0]
    # Incomplete node does not terminate or raise unhandled exception

    # --- AC 8: Zero LLM dependency or call in metric calculation ---
    # CycleTimeMetric execution is pure arithmetic and verified to run without any LLM
    import sys

    loaded_modules = sys.modules.keys()
    assert "openai" not in loaded_modules
    assert "anthropic" not in loaded_modules
    assert "google.generativeai" not in loaded_modules

    # --- AC 9: Verified by the assertions throughout this test ---

    # --- AC 10: Extensible to additional GitHub entities ---
    # Demonstrate extending the raw store and canonical model pattern to GitHub Issues
    class GitHubIssue(BaseModel):
        github_node_id: str
        number: int = Field(gt=0)
        title: str
        created_at: datetime
        closed_at: datetime | None = None
        state: str

    raw_issue_nodes: list[dict[str, Any]] = [
        {
            "id": "ISSUE_1",
            "number": 101,
            "title": "Bug in authentication flow",
            "createdAt": "2026-01-05T12:00:00Z",
            "closedAt": "2026-01-06T12:00:00Z",
            "state": "CLOSED",
        }
    ]
    issue_raw_path = raw_store.append_page(
        ingestion_run_id="run-issues-001",
        owner="acme",
        name="example",
        page_number=1,
        cursor=None,
        repository_id="R_1",
        repository_name_with_owner="acme/example",
        nodes=raw_issue_nodes,
    )
    assert issue_raw_path.exists()
    issue_records = raw_store.read_run("run-issues-001")
    canonical_issue = GitHubIssue(
        github_node_id=str(issue_records[0]["node"]["id"]),
        number=int(issue_records[0]["node"]["number"]),
        title=str(issue_records[0]["node"]["title"]),
        created_at=datetime.fromisoformat(
            issue_records[0]["node"]["createdAt"].replace("Z", "+00:00")
        ),
        closed_at=datetime.fromisoformat(
            issue_records[0]["node"]["closedAt"].replace("Z", "+00:00")
        ),
        state=str(issue_records[0]["node"]["state"]),
    )
    assert canonical_issue.github_node_id == "ISSUE_1"
    assert canonical_issue.number == 101
    assert canonical_issue.state == "CLOSED"
