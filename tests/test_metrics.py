from datetime import UTC, datetime

from gain.metrics.cycle_time import CycleTimeMetric
from gain.model.pr import PullRequest


def dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def pr(node_id: str, number: int, created: str, merged: str | None) -> PullRequest:
    return PullRequest(
        github_node_id=node_id,
        number=number,
        repository_name_with_owner="acme/example",
        repository_id="R_1",
        author_login="alice",
        author_type="User",
        created_at=dt(created),
        closed_at=dt(merged) if merged else None,
        merged_at=dt(merged) if merged else None,
        state="CLOSED" if merged else "OPEN",
        is_draft=False,
        additions=1,
        deletions=1,
        changed_files=1,
        review_decision=None,
        collected_at=datetime.now(UTC),
        ingestion_run_id="test-run",
    )


def test_cycle_time_reference_cases() -> None:
    prs = [
        pr("1", 1, "2026-01-01T00:00:00Z", "2026-01-01T06:00:00Z"),
        pr("2", 2, "2026-01-01T00:00:00Z", "2026-01-03T00:00:00Z"),
        pr("3", 3, "2026-01-01T00:00:00Z", None),
    ]
    observations = CycleTimeMetric.observations(prs)
    assert [x.cycle_time_seconds for x in observations] == [21600.0, 172800.0]
    summary = CycleTimeMetric.summary(observations)
    assert summary["count"] == 2
    assert summary["p50_seconds"] == 97200.0
    assert summary["p95_seconds"] == 165240.0


def test_cycle_time_excludes_unmerged_prs() -> None:
    observations = CycleTimeMetric.observations([pr("1", 1, "2026-01-01T00:00:00Z", None)])
    assert observations == []
