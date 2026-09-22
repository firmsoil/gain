from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import polars as pl

from gain.model.pr import PullRequest
from gain.storage.analytics import read_canonical, scan_canonical
from gain.storage.compaction import CompactionService
from gain.storage.partitioning import (
    CANONICAL_PR_SCHEMA,
    PartitionedReader,
    PartitionedWriter,
    compute_partition_dir,
    compute_partition_path,
)


def _make_pr(
    node_id: str,
    number: int,
    repo: str,
    created_at: datetime,
) -> PullRequest:
    return PullRequest(
        github_node_id=node_id,
        number=number,
        repository_name_with_owner=repo,
        repository_id=f"R_{node_id}",
        author_login="octodev",
        author_type="User",
        created_at=created_at,
        state="OPEN",
        is_draft=False,
        collected_at=datetime.now(UTC),
        ingestion_run_id="run-partition-test",
    )


def test_partition_path_generation() -> None:
    dt_utc = datetime(2026, 3, 14, 9, 30, tzinfo=UTC)
    path = compute_partition_path("pull_request", dt_utc, "firmsoil/gain")
    assert str(path) == "entity_type=pull_request/year=2026/month=03/org=firmsoil"

    # Non-UTC timezone conversion (e.g. UTC+5:30)
    tz_plus_5 = timezone(timedelta(hours=5, minutes=30))
    dt_tz = datetime(2026, 1, 1, 2, 0, tzinfo=tz_plus_5)  # UTC is 2025-12-31 20:30
    path_tz = compute_partition_path("issue", dt_tz, "acme")
    assert str(path_tz) == "entity_type=issue/year=2025/month=12/org=acme"

    # Naive datetime defaults to UTC
    dt_naive = datetime(2026, 7, 4, 12, 0)
    path_naive = compute_partition_path("deployment", dt_naive, "my-org")
    assert str(path_naive) == "entity_type=deployment/year=2026/month=07/org=my-org"

    # Absolute directory helper
    root = Path("/tmp/data/canonical")
    full_dir = compute_partition_dir(root, "pull_request", dt_utc, "firmsoil")
    assert full_dir == root / "entity_type=pull_request/year=2026/month=03/org=firmsoil"


def test_writing_partitioned_parquet_and_scanning(tmp_path: Path) -> None:
    root = tmp_path / "canonical"
    writer = PartitionedWriter(root)

    pr1 = _make_pr("PR_1", 1, "acme/frontend", datetime(2026, 1, 10, tzinfo=UTC))
    pr2 = _make_pr("PR_2", 2, "acme/backend", datetime(2026, 1, 20, tzinfo=UTC))
    pr3 = _make_pr("PR_3", 3, "other/repo", datetime(2026, 2, 15, tzinfo=UTC))

    written_paths = writer.write_canonical_prs([pr1, pr2, pr3])
    assert len(written_paths) == 2

    # Verify partition folder structure exists
    acme_jan = root / "entity_type=pull_request/year=2026/month=01/org=acme"
    other_feb = root / "entity_type=pull_request/year=2026/month=02/org=other"
    assert acme_jan.exists()
    assert other_feb.exists()
    assert len(list(acme_jan.glob("*.parquet"))) == 1
    assert len(list(other_feb.glob("*.parquet"))) == 1

    # Read partition file directly via read_canonical (verifying extra partition columns handled)
    jan_file = list(acme_jan.glob("*.parquet"))[0]
    jan_prs = read_canonical(jan_file)
    assert len(jan_prs) == 2
    assert {p.github_node_id for p in jan_prs} == {"PR_1", "PR_2"}

    # Scan with PartitionedReader and Polars Hive partitioning
    reader = PartitionedReader(root)
    lf = reader.scan(entity_type="pull_request")
    df = lf.collect()

    assert df.height == 3
    # Check hive partition columns are present
    assert "entity_type" in df.columns
    assert "year" in df.columns
    assert "month" in df.columns
    assert "org" in df.columns

    # Test Polars pushdown filtering by Hive columns
    acme_df = lf.filter(pl.col("org") == "acme").collect()
    assert acme_df.height == 2
    assert set(acme_df["github_node_id"].to_list()) == {"PR_1", "PR_2"}

    feb_df = lf.filter(pl.col("month") == 2).collect()
    assert feb_df.height == 1
    assert feb_df["github_node_id"][0] == "PR_3"


def test_partitioned_writer_dataframe_and_records(tmp_path: Path) -> None:
    root = tmp_path / "canonical"
    writer = PartitionedWriter(root)

    records = [
        {
            "github_node_id": "PR_10",
            "number": 10,
            "created_at": datetime(2026, 4, 1, tzinfo=UTC),
            "repository_name_with_owner": "firmsoil/core",
        },
        {
            "github_node_id": "PR_11",
            "number": 11,
            "created_at": datetime(2026, 4, 2, tzinfo=UTC),
            "repository_name_with_owner": "firmsoil/core",
        },
    ]

    paths = writer.write_records(records, entity_type="pull_request")
    assert len(paths) == 1
    assert paths[0].exists()
    assert not paths[0].with_suffix(".tmp").exists()

    # Empty inputs return empty lists
    assert writer.write_records([]) == []
    assert writer.write_canonical_prs([]) == []
    assert writer.write_dataframe(pl.DataFrame()) == []


def test_reader_flat_scanning_fallback(tmp_path: Path) -> None:
    root = tmp_path / "canonical_flat"
    root.mkdir(parents=True, exist_ok=True)

    # Write legacy flat Parquet files directly under canonical dir
    df1 = pl.DataFrame({"github_node_id": ["PR_100"], "number": [100]})
    df2 = pl.DataFrame({"github_node_id": ["PR_101"], "number": [101]})
    df1.write_parquet(root / "pull_requests__01.parquet")
    df2.write_parquet(root / "pull_requests__02.parquet")

    reader = PartitionedReader(root)
    lf = reader.scan(entity_type="pull_request")
    df = lf.collect()

    assert df.height == 2
    assert set(df["github_node_id"].to_list()) == {"PR_100", "PR_101"}


def test_scan_canonical_empty_fallback(tmp_path: Path) -> None:
    non_existent = tmp_path / "missing_dir"
    empty_dir = tmp_path / "empty_dir"
    empty_dir.mkdir(parents=True, exist_ok=True)

    lf_missing = scan_canonical(non_existent, entity_type="pull_request")
    df_missing = lf_missing.collect()
    assert df_missing.height == 0
    assert set(df_missing.columns) == set(CANONICAL_PR_SCHEMA.keys())

    lf_empty = scan_canonical(empty_dir, entity_type="pull_request")
    df_empty = lf_empty.collect()
    assert df_empty.height == 0
    assert set(df_empty.columns) == set(CANONICAL_PR_SCHEMA.keys())


def test_compaction_service_single_partition(tmp_path: Path) -> None:
    part_dir = tmp_path / "entity_type=pull_request/year=2026/month=01/org=acme"
    part_dir.mkdir(parents=True, exist_ok=True)

    # Write 3 small parquet files
    df1 = pl.DataFrame({"id": [1, 2], "name": ["a", "b"]})
    df2 = pl.DataFrame({"id": [3, 4], "name": ["c", "d"]})
    df3 = pl.DataFrame({"id": [5], "name": ["e"]})

    df1.write_parquet(part_dir / "part_1.parquet")
    df2.write_parquet(part_dir / "part_2.parquet")
    df3.write_parquet(part_dir / "part_3.parquet")

    assert len(list(part_dir.glob("*.parquet"))) == 3

    compactor = CompactionService(target_file_size_bytes=1024 * 1024, min_file_count=2)
    compacted_file = compactor.compact_partition(part_dir)

    assert compacted_file is not None
    assert compacted_file.exists()

    # The 3 small files should have been removed, leaving only 1 compacted file
    remaining_parquet = list(part_dir.glob("*.parquet"))
    assert len(remaining_parquet) == 1
    assert remaining_parquet[0] == compacted_file

    # No leftover .tmp files
    assert list(part_dir.glob("*.tmp")) == []

    # Compacted file should contain all 5 records
    compacted_df = pl.read_parquet(compacted_file)
    assert compacted_df.height == 5
    assert compacted_df["id"].to_list() == [1, 2, 3, 4, 5]

    # Calling compact again when only 1 file is present should return None
    assert compactor.compact_partition(part_dir) is None


def test_compaction_service_compact_all(tmp_path: Path) -> None:
    root = tmp_path / "canonical"
    p1 = root / "entity_type=pull_request/year=2026/month=01/org=acme"
    p2 = root / "entity_type=pull_request/year=2026/month=02/org=acme"
    p3 = root / "entity_type=pull_request/year=2026/month=03/org=acme"
    p1.mkdir(parents=True, exist_ok=True)
    p2.mkdir(parents=True, exist_ok=True)
    p3.mkdir(parents=True, exist_ok=True)

    # p1 has 2 small files -> compacted
    pl.DataFrame({"val": [1]}).write_parquet(p1 / "file1.parquet")
    pl.DataFrame({"val": [2]}).write_parquet(p1 / "file2.parquet")

    # p2 has 3 small files -> compacted
    pl.DataFrame({"val": [3]}).write_parquet(p2 / "file1.parquet")
    pl.DataFrame({"val": [4]}).write_parquet(p2 / "file2.parquet")
    pl.DataFrame({"val": [5]}).write_parquet(p2 / "file3.parquet")

    # p3 has 1 small file -> not compacted
    pl.DataFrame({"val": [6]}).write_parquet(p3 / "file1.parquet")

    compactor = CompactionService(min_file_count=2)
    compacted = compactor.compact_all(root)

    assert len(compacted) == 2
    assert len(list(p1.glob("*.parquet"))) == 1
    assert len(list(p2.glob("*.parquet"))) == 1
    assert len(list(p3.glob("*.parquet"))) == 1


def test_compaction_service_lock_prevents_concurrent_runs(tmp_path: Path) -> None:
    part_dir = tmp_path / "entity_type=pull_request/year=2026/month=04/org=acme"
    part_dir.mkdir(parents=True, exist_ok=True)

    pl.DataFrame({"id": [1]}).write_parquet(part_dir / "f1.parquet")
    pl.DataFrame({"id": [2]}).write_parquet(part_dir / "f2.parquet")

    # Simulate existing lock file from another concurrent worker
    lock_file = part_dir / ".compaction.lock"
    lock_file.touch()

    compactor = CompactionService(min_file_count=2)
    result = compactor.compact_partition(part_dir)

    # Should safely skip and return None without touching files
    assert result is None
    assert len(list(part_dir.glob("*.parquet"))) == 2
    assert lock_file.exists()
    lock_file.unlink()

    # Now with lock removed, compaction succeeds
    result2 = compactor.compact_partition(part_dir)
    assert result2 is not None
    assert len(list(part_dir.glob("*.parquet"))) == 1
    assert not lock_file.exists()
