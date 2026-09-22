from __future__ import annotations

import json
from pathlib import Path

from gain.config import Settings
from gain.services.lineage import LineageService
from gain.storage.analytics import write_canonical
from gain.storage.index import EntityIndex
from gain.storage.relationships import RelationshipStore
from tests.factories import make_pr


def test_entity_index_record_and_lookup(tmp_path: Path) -> None:
    index = EntityIndex(index_dir=tmp_path / "indexes")

    records = [
        {
            "github_node_id": "PR_kwDO1234",
            "number": 101,
            "repository_name_with_owner": "firmsoil/gain",
            "state": "MERGED",
        },
        {
            "github_node_id": "PR_kwDO5678",
            "number": 102,
            "repository_name_with_owner": "firmsoil/gain",
            "state": "OPEN",
        },
    ]

    location = "/data/canonical/pr_batch_1.parquet"
    index.index_records("pull_request", records, location=location)

    # Lookup by github_node_id
    res1 = index.lookup("pr", "PR_kwDO1234")
    assert res1 is not None
    assert res1["location"] == location
    assert res1["number"] == 101
    assert res1["entity_type"] == "pr"

    # Lookup by PR number
    res2 = index.lookup("pr", "101")
    assert res2 is not None
    assert res2["identifier"] == "101"
    assert res2["location"] == location

    # Lookup using alias
    res_alias = index.lookup("pull_request", "PR_kwDO5678")
    assert res_alias is not None
    assert res_alias["number"] == 102

    # Lookup non-existent
    assert index.lookup("pr", "UNKNOWN_ID") is None
    assert index.lookup("issue", "PR_kwDO1234") is None


def test_entity_index_persistence(tmp_path: Path) -> None:
    index_dir = tmp_path / "indexes"
    index1 = EntityIndex(index_dir=index_dir)
    index1.index_entity(
        entity_type="issue",
        identifier="GAIN-101",
        location="/data/issues/jira.parquet",
        metadata={"priority": "High", "story_points": 5},
    )

    assert (index_dir / "entity_index.json").exists()

    # Create fresh index instance and verify it loads from disk
    index2 = EntityIndex(index_dir=index_dir)
    result = index2.lookup("issue", "GAIN-101")
    assert result is not None
    assert result["location"] == "/data/issues/jira.parquet"
    assert result["priority"] == "High"
    assert result["story_points"] == 5


def test_entity_index_raw_and_nested(tmp_path: Path) -> None:
    index = EntityIndex(index_dir=tmp_path / "indexes")

    raw_records = [
        {
            "node": {"id": "PR_raw_001", "number": 42, "title": "Test PR"},
            "cursor": "cursor_xyz",
            "page_number": 3,
            "line_number": 15,
        }
    ]

    raw_loc = "/data/raw/raw_pull_requests_2026.jsonl"
    index.index_records("raw", raw_records, location=raw_loc)

    # Lookup by node ID
    by_id = index.lookup("raw", "PR_raw_001")
    assert by_id is not None
    assert by_id["location"] == raw_loc
    assert by_id["line_number"] == 15
    assert by_id["cursor"] == "cursor_xyz"
    assert by_id["page_number"] == 3

    # Lookup by PR number
    by_num = index.lookup("raw", "42")
    assert by_num is not None
    assert by_num["location"] == raw_loc


def test_entity_index_helpers(tmp_path: Path) -> None:
    index = EntityIndex(index_dir=tmp_path / "indexes")
    assert index.count() == 0

    index.index_entity("commit", "c0ffee1234", "/data/commits.parquet")
    assert index.contains("commit", "c0ffee1234")
    assert not index.contains("commit", "unknown")
    assert index.count("commit") == 1
    assert index.count() == 1

    # Custom identifier key
    index.index_records(
        "custom",
        [{"custom_key": "CK-99", "name": "Custom Entity"}],
        location="/data/custom.parquet",
        identifier_key="custom_key",
    )
    assert index.lookup("custom", "CK-99") is not None

    # Clear
    index.clear()
    assert index.count() == 0
    assert not (tmp_path / "indexes" / "entity_index.json").exists()


def test_relationship_store_pr_issue_links(tmp_path: Path) -> None:
    store = RelationshipStore(storage_dir=tmp_path / "relationships")

    # Record PR -> Issue links
    store.record_pr_issue_link("firmsoil/gain", 101, "GAIN-10")
    store.record_pr_issue_link("firmsoil/gain", 101, "GAIN-20")
    store.record_pr_issue_link("firmsoil/gain", 102, "GAIN-20")

    # Idempotent re-recording
    store.record_pr_issue_link("firmsoil/gain", 101, "GAIN-10")

    # Query issues linked to PR
    issues_101 = store.get_linked_issues("firmsoil/gain", 101)
    assert issues_101 == ["GAIN-10", "GAIN-20"]

    issues_102 = store.get_linked_issues("firmsoil/gain", 102)
    assert issues_102 == ["GAIN-20"]

    assert store.get_linked_issues("firmsoil/gain", 999) == []

    # Query PRs linked to Issue
    prs_gain_20 = store.get_linked_prs("GAIN-20")
    assert len(prs_gain_20) == 2
    assert {"repository": "firmsoil/gain", "pr_number": 101} in prs_gain_20
    assert {"repository": "firmsoil/gain", "pr_number": 102} in prs_gain_20

    prs_gain_10 = store.get_linked_prs("GAIN-10")
    assert prs_gain_10 == [{"repository": "firmsoil/gain", "pr_number": 101}]

    assert store.get_linked_prs("GAIN-UNKNOWN") == []


def test_relationship_store_persistence(tmp_path: Path) -> None:
    storage_dir = tmp_path / "relationships"
    store1 = RelationshipStore(storage_dir=storage_dir)
    store1.record_pr_issue_link("firmsoil/gain", 50, "GAIN-500")

    assert (storage_dir / "relationships.parquet").exists()

    # Re-open from another instance
    store2 = RelationshipStore(storage_dir=storage_dir)
    assert store2.get_linked_issues("firmsoil/gain", 50) == ["GAIN-500"]
    assert store2.get_linked_prs("GAIN-500") == [{"repository": "firmsoil/gain", "pr_number": 50}]

    df = store2.as_dataframe()
    assert len(df) == 1
    assert df["rel_type"][0] == "pr_issue"


def test_relationship_store_commit_deployment_links(tmp_path: Path) -> None:
    store = RelationshipStore(storage_dir=tmp_path / "relationships")

    store.record_commit_deployment_link("a1b2c3d4", "deploy_prod_100")
    store.record_commit_deployment_link("a1b2c3d4", "deploy_canary_101")
    # Idempotent call
    store.record_commit_deployment_link("a1b2c3d4", "deploy_prod_100")

    deps = store.get_linked_deployments("a1b2c3d4")
    assert deps == ["deploy_prod_100", "deploy_canary_101"]

    commits = store.get_linked_commits("deploy_prod_100")
    assert commits == ["a1b2c3d4"]

    assert store.get_linked_deployments("unknown_sha") == []
    assert store.get_linked_commits("unknown_deploy") == []

    store.clear()
    assert store.get_linked_deployments("a1b2c3d4") == []
    assert not (tmp_path / "relationships" / "relationships.parquet").exists()


def test_lineage_service_fallback_without_index(tmp_path: Path) -> None:
    canonical_dir = tmp_path / "canonical"
    raw_dir = tmp_path / "raw"
    indexes_dir = tmp_path / "indexes"
    canonical_dir.mkdir(parents=True)
    raw_dir.mkdir(parents=True)

    # Create canonical PR parquet
    pr = make_pr(github_node_id="PR_NODE_001", number=10)
    write_canonical([pr], canonical_dir / "pr_test.parquet")

    # Create raw JSONL
    raw_file = raw_dir / "raw_pr_test.jsonl"
    with raw_file.open("w", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "node": {"id": "PR_NODE_001", "number": 10},
                    "cursor": "cursor_test_1",
                    "page_number": 1,
                }
            )
            + "\n"
        )

    settings = Settings(
        output_dir=tmp_path,
        canonical_dir=canonical_dir,
        raw_dir=raw_dir,
        indexes_dir=indexes_dir,
    )

    service = LineageService(settings=settings)
    trace = service.get_pr_lineage("PR_NODE_001")

    assert trace is not None
    assert trace.target_id == "PR_NODE_001"
    assert trace.target_type == "PullRequest"
    assert len(trace.nodes) == 3

    # Raw node verification
    raw_node = trace.nodes[0]
    assert raw_node.layer == "raw"
    assert raw_node.metadata["raw_file"] == "raw_pr_test.jsonl"
    assert raw_node.metadata["line_number"] == 1
    assert raw_node.metadata["cursor"] == "cursor_test_1"

    # Canonical node verification
    canon_node = trace.nodes[1]
    assert canon_node.layer == "canonical"
    assert canon_node.metadata["file"] == "pr_test.parquet"
    assert canon_node.metadata["number"] == 10

    # Metric node verification
    metric_node = trace.nodes[2]
    assert metric_node.layer == "metric_observation"
    assert metric_node.metadata["metric_id"] == "GAIN-PR-001"

    assert len(trace.provenance_chain) == 3

    # Non-existent node lookup returns None
    assert service.get_pr_lineage("NON_EXISTENT") is None


def test_lineage_service_with_prebuilt_index(tmp_path: Path) -> None:
    canonical_dir = tmp_path / "canonical"
    raw_dir = tmp_path / "raw"
    indexes_dir = tmp_path / "indexes"
    canonical_dir.mkdir(parents=True)
    raw_dir.mkdir(parents=True)

    pr = make_pr(github_node_id="PR_NODE_INDEXED_002", number=20)
    write_canonical([pr], canonical_dir / "pr_test.parquet")

    raw_file = raw_dir / "raw_pr_test.jsonl"
    with raw_file.open("w", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "node": {"id": "PR_NODE_INDEXED_002", "number": 20},
                    "cursor": "cur_indexed",
                    "page_number": 2,
                }
            )
            + "\n"
        )

    settings = Settings(
        output_dir=tmp_path,
        canonical_dir=canonical_dir,
        raw_dir=raw_dir,
        indexes_dir=indexes_dir,
    )

    # Build index upfront
    index = EntityIndex(index_dir=indexes_dir)
    indexed_canonical = index.index_canonical_prs(canonical_dir)
    assert indexed_canonical == 1
    indexed_raw = index.index_raw_prs(raw_dir)
    assert indexed_raw == 1

    # Verify lookups in index
    assert index.lookup("pr", "PR_NODE_INDEXED_002") is not None
    assert index.lookup("raw", "PR_NODE_INDEXED_002") is not None

    # Run LineageService with index
    service = LineageService(settings=settings, index=index)
    trace = service.get_pr_lineage("PR_NODE_INDEXED_002")

    assert trace is not None
    assert trace.target_id == "PR_NODE_INDEXED_002"
    assert trace.nodes[0].layer == "raw"
    assert trace.nodes[0].metadata["raw_file"] == "raw_pr_test.jsonl"
    assert trace.nodes[0].metadata["line_number"] == 1
    assert trace.nodes[1].layer == "canonical"
    assert trace.nodes[1].metadata["file"] == "pr_test.parquet"

    # Test relationship querying via LineageService
    service.relationships.record_pr_issue_link("test-org/test-repo", 20, "GAIN-200")
    linked_issues = service.get_pr_linked_issues("test-org/test-repo", 20)
    assert linked_issues == ["GAIN-200"]

    linked_prs = service.get_issue_linked_prs("GAIN-200")
    assert linked_prs == [{"repository": "test-org/test-repo", "pr_number": 20}]


def test_lineage_service_non_existent_canonical_dir(tmp_path: Path) -> None:
    settings = Settings(
        output_dir=tmp_path,
        canonical_dir=tmp_path / "non_existent_canonical",
        raw_dir=tmp_path / "raw",
        indexes_dir=tmp_path / "indexes",
    )
    service = LineageService(settings=settings)
    assert service.get_pr_lineage("ANY_NODE") is None
