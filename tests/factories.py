from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from gain.model.pr import PullRequest


class _Missing:
    pass


MISSING = _Missing()


def make_pr(
    *,
    github_node_id: str = "PR_test001",
    number: int = 1,
    repository_name_with_owner: str = "test-org/test-repo",
    repository_id: str = "R_test001",
    author_login: str | None = "test-author",
    author_type: str | None = "User",
    created_at: datetime | None = None,
    closed_at: Any = MISSING,
    merged_at: Any = MISSING,
    state: str = "MERGED",
    is_draft: bool = False,
    additions: int | None = 10,
    deletions: int | None = 5,
    changed_files: int | None = 2,
    review_decision: str | None = "APPROVED",
    collected_at: datetime | None = None,
    ingestion_run_id: str = "test-run-001",
) -> PullRequest:
    """Create a PullRequest with sensible defaults for testing."""
    now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC)

    if state == "OPEN":
        if merged_at is MISSING:
            merged_at = None
        if closed_at is MISSING:
            closed_at = None
    else:
        if merged_at is MISSING:
            merged_at = datetime(2026, 6, 12, 14, 30, 0, tzinfo=UTC)
        if closed_at is MISSING:
            closed_at = datetime(2026, 6, 12, 14, 30, 0, tzinfo=UTC)

    return PullRequest(
        github_node_id=github_node_id,
        number=number,
        repository_name_with_owner=repository_name_with_owner,
        repository_id=repository_id,
        author_login=author_login,
        author_type=author_type,
        created_at=created_at or datetime(2026, 6, 10, 10, 0, 0, tzinfo=UTC),
        closed_at=closed_at,
        merged_at=merged_at,
        state=state,
        is_draft=is_draft,
        additions=additions,
        deletions=deletions,
        changed_files=changed_files,
        review_decision=review_decision,
        collected_at=collected_at or now,
        ingestion_run_id=ingestion_run_id,
    )
