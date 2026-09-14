from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from gain.metrics.monthly_stats import MonthlyPRStats, MonthlyStatsMetric
from gain.model.pr import PullRequest
from gain.storage.analytics import read_monthly_stats, write_monthly_stats


def dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def make_pr(
    node_id: str,
    number: int,
    created: str,
    closed: str | None = None,
    merged: str | None = None,
    repo: str = "acme/example",
    author: str = "alice",
    author_type: str = "User",
) -> PullRequest:
    state = "CLOSED" if (closed or merged) else "OPEN"
    return PullRequest(
        github_node_id=node_id,
        number=number,
        repository_name_with_owner=repo,
        repository_id="R_1",
        author_login=author,
        author_type=author_type,
        created_at=dt(created),
        closed_at=dt(closed) if closed else None,
        merged_at=dt(merged) if merged else None,
        state=state,
        is_draft=False,
        additions=10,
        deletions=5,
        changed_files=2,
        review_decision=None,
        collected_at=datetime.now(UTC),
        ingestion_run_id="test-run",
    )


def test_empty_prs_generates_zero_filled_timeline() -> None:
    ref = dt("2026-08-31T23:59:59Z")
    stats = MonthlyStatsMetric.calculate([], months=12, reference_date=ref)
    assert len(stats) == 12
    assert stats[0].month == "2025-09"
    assert stats[-1].month == "2026-08"
    assert all(s.created_count == 0 for s in stats)
    assert all(s.merged_count == 0 for s in stats)
    assert all(s.closed_count == 0 for s in stats)
    assert all(s.closed_unmerged_count == 0 for s in stats)
    assert all(s.merge_rate_pct is None for s in stats)


def test_monthly_distribution_accuracy() -> None:
    ref = dt("2026-08-31T23:59:59Z")
    prs = [
        make_pr("1", 1, "2025-09-10T10:00:00Z", "2025-09-12T10:00:00Z", "2025-09-12T10:00:00Z"),
        make_pr("2", 2, "2025-10-01T08:00:00Z", "2025-10-05T09:00:00Z", None),
        make_pr("3", 3, "2025-10-25T14:00:00Z", "2025-11-02T11:00:00Z", "2025-11-02T11:00:00Z"),
        make_pr("4", 4, "2025-11-15T12:00:00Z", None, None),
    ]

    stats = MonthlyStatsMetric.calculate(prs, months=12, reference_date=ref)
    by_month = {s.month: s for s in stats}

    sep = by_month["2025-09"]
    assert sep.created_count == 1
    assert sep.merged_count == 1
    assert sep.closed_count == 1
    assert sep.closed_unmerged_count == 0
    assert sep.merge_rate_pct == 100.0

    oct_stat = by_month["2025-10"]
    assert oct_stat.created_count == 2
    assert oct_stat.merged_count == 0
    assert oct_stat.closed_count == 1
    assert oct_stat.closed_unmerged_count == 1
    assert oct_stat.merge_rate_pct == 0.0

    nov = by_month["2025-11"]
    assert nov.created_count == 1
    assert nov.merged_count == 1
    assert nov.closed_count == 1
    assert nov.closed_unmerged_count == 0
    assert nov.merge_rate_pct == 100.0


def test_monthly_stats_by_author() -> None:
    ref = dt("2026-08-31T23:59:59Z")
    prs = [
        make_pr(
            "1", 1, "2026-08-01T10:00:00Z", "2026-08-01T12:00:00Z",
            "2026-08-01T12:00:00Z", author="alice",
        ),
        make_pr(
            "2", 2, "2026-08-02T10:00:00Z", "2026-08-03T12:00:00Z",
            "2026-08-03T12:00:00Z", author="bob",
        ),
        make_pr("3", 3, "2026-08-05T10:00:00Z", None, None, author="alice"),
    ]

    stats = MonthlyStatsMetric.calculate(prs, months=1, reference_date=ref, by_author=True)
    assert len(stats) == 2  # 1 month x 2 authors

    by_author = {s.author: s for s in stats}
    alice_stat = by_author["alice"]
    assert alice_stat.created_count == 2
    assert alice_stat.merged_count == 1

    bob_stat = by_author["bob"]
    assert bob_stat.created_count == 1
    assert bob_stat.merged_count == 1


def test_bot_filtering_in_author_stats() -> None:
    ref = dt("2026-08-31T23:59:59Z")
    prs = [
        make_pr(
            "1", 1, "2026-08-01T10:00:00Z", "2026-08-01T12:00:00Z",
            "2026-08-01T12:00:00Z", author="alice",
        ),
        make_pr(
            "2", 2, "2026-08-02T10:00:00Z", "2026-08-02T10:05:00Z",
            "2026-08-02T10:05:00Z", author="dependabot[bot]", author_type="Bot",
        ),
    ]

    # Without bots
    human_stats = MonthlyStatsMetric.calculate(
        prs, months=1, reference_date=ref, by_author=True, include_bots=False
    )
    authors = {s.author for s in human_stats}
    assert authors == {"alice"}

    # With bots
    all_stats = MonthlyStatsMetric.calculate(
        prs, months=1, reference_date=ref, by_author=True, include_bots=True
    )
    authors_all = {s.author for s in all_stats}
    assert authors_all == {"alice", "dependabot[bot]"}


def test_format_table_responsible_use_advisory() -> None:
    stats = [
        MonthlyPRStats(
            month="2026-08",
            created_count=5,
            merged_count=4,
            closed_count=4,
            closed_unmerged_count=0,
            merge_rate_pct=100.0,
            author="alice",
        ),
    ]
    table_str = MonthlyStatsMetric.format_table(stats)
    assert "RESPONSIBLE USE ADVISORY" in table_str
    assert "Author" in table_str
    assert "alice" in table_str


def test_storage_roundtrip(tmp_path: Path) -> None:
    stats = [
        MonthlyPRStats(
            month="2026-01",
            created_count=10,
            merged_count=8,
            closed_count=9,
            closed_unmerged_count=1,
            merge_rate_pct=88.9,
            repository=None,
            author="alice",
            author_type="User",
        )
    ]
    path = tmp_path / "test-monthly-stats.parquet"
    write_monthly_stats(stats, path)
    assert path.exists()

    loaded = read_monthly_stats(path)
    assert len(loaded) == 1
    assert loaded[0].month == "2026-01"
    assert loaded[0].created_count == 10
    assert loaded[0].merged_count == 8
    assert loaded[0].closed_count == 9
    assert loaded[0].closed_unmerged_count == 1
    assert loaded[0].merge_rate_pct == 88.9
    assert loaded[0].author == "alice"
    assert loaded[0].author_type == "User"
