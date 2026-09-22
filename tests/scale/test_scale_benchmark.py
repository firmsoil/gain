from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from tests.factories import make_pr

from gain.config import Settings
from gain.model.pr import PullRequest
from gain.services.metrics import MetricService
from gain.storage.partitioning import PartitionedWriter


def test_scale_ingestion_and_query_performance(tmp_path: Path) -> None:
    """Scale benchmark: 10,000 synthetic PRs across 50 repositories.

    Validates that Polars streaming query execution completes well within the 2.0s SLO.
    """
    canonical_dir = tmp_path / "canonical"
    writer = PartitionedWriter(canonical_dir)

    base_time = datetime(2026, 1, 1, tzinfo=UTC)
    num_repos = 50
    prs_per_repo = 200  # 50 * 200 = 10,000 total PRs

    records: list[PullRequest] = []
    for r_idx in range(num_repos):
        repo_name = f"firmsoil/service-{r_idx:02d}"
        for p_idx in range(prs_per_repo):
            created = base_time + timedelta(hours=p_idx * 2)
            closed = created + timedelta(hours=12 + (p_idx % 48))
            pr = make_pr(
                number=p_idx + 1,
                repository_name_with_owner=repo_name,
                author_login=f"developer_{p_idx % 20}",
                created_at=created,
                closed_at=closed,
                merged_at=closed,
                state="MERGED",
                ingestion_run_id="scale-run-10k",
            )
            records.append(pr)

    # 1. Write partitioned dataset
    write_start = time.monotonic()
    written_files = writer.write_canonical_prs(records)
    write_duration = time.monotonic() - write_start
    assert write_duration > 0
    assert len(written_files) > 0

    # 2. Benchmark Single Repository Query with Predicate Pushdown
    settings = Settings(canonical_dir=canonical_dir)
    service = MetricService(settings=settings)
    query_start = time.monotonic()
    result = service.query_pr_cycle_time(
        repository="firmsoil/service-00",
        start_date=datetime(2026, 1, 1, tzinfo=UTC),
        end_date=datetime(2026, 3, 1, tzinfo=UTC),
    )
    query_duration = time.monotonic() - query_start

    # Verify query latency is well within 2.0s SLO target (typically < 0.1s in Polars)
    assert query_duration < 2.0, f"Query latency {query_duration:.3f}s exceeded 2.0s SLO"
    assert result.total_evaluated > 0
    assert result.merged_count > 0
    assert result.summary_stats["p50_seconds"] is not None

    # 3. Benchmark All-Repositories Aggregation
    all_start = time.monotonic()
    all_result = service.query_pr_cycle_time(
        start_date=datetime(2026, 1, 1, tzinfo=UTC),
        end_date=datetime(2026, 3, 1, tzinfo=UTC),
    )
    all_duration = time.monotonic() - all_start
    assert all_duration < 3.0, f"Cross-repository aggregation {all_duration:.3f}s too slow"
    assert all_result.total_evaluated == len(records)
