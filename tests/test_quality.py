from __future__ import annotations

from datetime import UTC, datetime

from gain.model.pr import PullRequest
from gain.quality import validate_pull_requests


def _make_pr(
    node_id: str = "PR_1",
    created_at: datetime | None = None,
    closed_at: datetime | None = None,
    merged_at: datetime | None = None,
) -> PullRequest:
    created = created_at or datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    return PullRequest(
        github_node_id=node_id,
        number=1,
        repository_name_with_owner="acme/example",
        repository_id="R_1",
        author_login="developer",
        author_type="User",
        created_at=created,
        closed_at=closed_at,
        merged_at=merged_at,
        state="CLOSED" if closed_at else "OPEN",
        is_draft=False,
        collected_at=datetime.now(UTC),
        ingestion_run_id="run-quality-001",
    )


def test_quality_valid_pull_requests() -> None:
    prs = [
        _make_pr(
            node_id="PR_1",
            created_at=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
            closed_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
            merged_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        ),
        _make_pr(
            node_id="PR_2",
            created_at=datetime(2026, 1, 2, 10, 0, tzinfo=UTC),
            closed_at=None,
            merged_at=None,
        ),
    ]
    issues = validate_pull_requests(prs)
    assert len(issues) == 0


def test_quality_duplicate_node_id() -> None:
    prs = [
        _make_pr(node_id="PR_DUP"),
        _make_pr(node_id="PR_DUP"),
    ]
    issues = validate_pull_requests(prs)
    assert len(issues) == 1
    assert issues[0].code == "DUPLICATE_NODE_ID"
    assert issues[0].severity == "ERROR"
    assert issues[0].github_node_id == "PR_DUP"


def test_quality_closed_at_precedes_created_at() -> None:
    pr = _make_pr(
        node_id="PR_TIME_SKEW_1",
        created_at=datetime(2026, 1, 2, 12, 0, tzinfo=UTC),
        closed_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
    )
    issues = validate_pull_requests([pr])
    assert len(issues) == 1
    assert issues[0].code == "INVALID_CLOSED_AT"
    assert issues[0].severity == "ERROR"


def test_quality_merged_at_precedes_created_at() -> None:
    pr = _make_pr(
        node_id="PR_TIME_SKEW_2",
        created_at=datetime(2026, 1, 2, 12, 0, tzinfo=UTC),
        closed_at=datetime(2026, 1, 2, 13, 0, tzinfo=UTC),
        merged_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
    )
    issues = validate_pull_requests([pr])
    assert len(issues) == 1
    assert issues[0].code == "INVALID_MERGED_AT"
    assert issues[0].severity == "ERROR"


def test_quality_merged_without_closed_at() -> None:
    pr = _make_pr(
        node_id="PR_ANOMALY",
        created_at=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
        closed_at=None,
        merged_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
    )
    issues = validate_pull_requests([pr])
    assert len(issues) == 1
    assert issues[0].code == "MERGED_WITHOUT_CLOSED_AT"
    assert issues[0].severity == "WARNING"
