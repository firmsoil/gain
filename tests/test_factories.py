from __future__ import annotations

from datetime import UTC, datetime

from tests.factories import make_pr


def test_make_pr_default() -> None:
    pr = make_pr()
    assert pr.github_node_id == "PR_test001"
    assert pr.state == "MERGED"
    assert pr.merged_at == datetime(2026, 6, 12, 14, 30, 0, tzinfo=UTC)
    assert pr.closed_at == datetime(2026, 6, 12, 14, 30, 0, tzinfo=UTC)
    assert pr.created_at == datetime(2026, 6, 10, 10, 0, 0, tzinfo=UTC)


def test_make_pr_open() -> None:
    pr = make_pr(state="OPEN")
    assert pr.state == "OPEN"
    assert pr.merged_at is None
    assert pr.closed_at is None


def test_make_pr_custom() -> None:
    custom_date = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    pr = make_pr(github_node_id="PR_custom", state="CLOSED", merged_at=None, closed_at=custom_date)
    assert pr.github_node_id == "PR_custom"
    assert pr.state == "CLOSED"
    assert pr.merged_at is None
    assert pr.closed_at == custom_date
