from __future__ import annotations

from dataclasses import dataclass

from gain.model.pr import PullRequest


@dataclass(frozen=True)
class QualityIssue:
    severity: str
    code: str
    message: str
    github_node_id: str


def validate_pull_requests(prs: list[PullRequest]) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    seen: set[str] = set()
    for pr in prs:
        if pr.github_node_id in seen:
            issues.append(QualityIssue("ERROR", "DUPLICATE_NODE_ID", "Duplicate GitHub node ID", pr.github_node_id))
        seen.add(pr.github_node_id)
        if pr.closed_at and pr.closed_at < pr.created_at:
            issues.append(QualityIssue("ERROR", "INVALID_CLOSED_AT", "closed_at precedes created_at", pr.github_node_id))
        if pr.merged_at and pr.merged_at < pr.created_at:
            issues.append(QualityIssue("ERROR", "INVALID_MERGED_AT", "merged_at precedes created_at", pr.github_node_id))
        if pr.merged_at and not pr.closed_at:
            issues.append(QualityIssue("WARNING", "MERGED_WITHOUT_CLOSED_AT", "Merged PR has no closed_at", pr.github_node_id))
    return issues
