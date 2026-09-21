"""Deterministic issue analytics and cross-system traceability service."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field

from gain.config import Settings, get_settings
from gain.mcp.schemas.ai import ClaimClassification
from gain.model.issue import CanonicalIssue
from gain.model.pr import PullRequest
from gain.services.metrics import MetricService
from gain.storage.issues import load_issues_for_project_or_repo


class IssueAnalyticsResult(BaseModel):
    """Deterministic issue analytics and cycle-time distributions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: str
    project_key: str | None
    classification: ClaimClassification
    total_issues: int
    resolved_issues: int
    open_issues: int
    cycle_time_stats: dict[str, float | None]
    issues_by_type: dict[str, int]
    linked_prs_count: int
    traceability_rate: float = Field(
        description="Percentage of resolved issues linked to canonical PRs (0.0 to 100.0)"
    )
    findings: list[str]
    limitations: list[str]


class IssueAnalyticsService:
    """Computes deterministic flow and cycle time metrics for enterprise work items."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.metric_service = MetricService(self.settings)

    def analyze_issues(
        self,
        project_key: str | None = None,
        repository: str | None = None,
    ) -> IssueAnalyticsResult:
        """Analyze issue velocity, cycle times, and PR traceability."""
        issues = load_issues_for_project_or_repo(
            project_key=project_key,
            canonical_dir=self.settings.canonical_dir,
        )

        if not issues:
            return IssueAnalyticsResult(
                status="insufficient_data",
                project_key=project_key,
                classification=ClaimClassification.UNKNOWN,
                total_issues=0,
                resolved_issues=0,
                open_issues=0,
                cycle_time_stats={},
                issues_by_type={},
                linked_prs_count=0,
                traceability_rate=0.0,
                findings=[],
                limitations=[
                    f"No canonical issues found in storage for project_key='{project_key}'."
                ],
            )

        resolved = [i for i in issues if i.is_resolved]
        open_issues = [i for i in issues if not i.is_resolved]

        # 1. Cycle time distribution
        cycle_times = [
            i.cycle_time_seconds() for i in resolved if i.cycle_time_seconds() is not None
        ]
        cycle_times_valid = [t for t in cycle_times if t is not None]

        stats: dict[str, float | None] = {}
        if cycle_times_valid:
            cycle_times_valid.sort()
            n = len(cycle_times_valid)
            stats = {
                "count": float(n),
                "p50_seconds": round(cycle_times_valid[int(n * 0.50)], 1),
                "p75_seconds": round(cycle_times_valid[int(n * 0.75)], 1),
                "p90_seconds": round(cycle_times_valid[min(int(n * 0.90), n - 1)], 1),
                "mean_seconds": round(sum(cycle_times_valid) / n, 1),
            }

        # 2. Breakdown by type
        by_type: dict[str, int] = {}
        for i in issues:
            type_name = str(i.issue_type.value)
            by_type[type_name] = by_type.get(type_name, 0) + 1

        # 3. Cross-system PR traceability
        all_prs = (
            self.metric_service._load_canonical_prs(repository=repository)
            if repository
            else self._load_all_prs()
        )
        linked_count, trace_rate = self._evaluate_traceability(issues, all_prs)

        p50_str = f"{stats.get('p50_seconds', 0.0):.1f}s" if stats else "N/A"
        findings = [
            (
                f"Evaluated {len(issues)} canonical issues ({len(resolved)} resolved, "
                f"{len(open_issues)} open) across project '{project_key or 'all'}'."
            ),
            f"Median issue cycle time (created to resolved): {p50_str}.",
            (
                f"Cross-system traceability rate: {trace_rate:.1f}% "
                f"({linked_count} issues linked to PRs)."
            ),
        ]

        return IssueAnalyticsResult(
            status="available",
            project_key=project_key,
            classification=ClaimClassification.DERIVED,
            total_issues=len(issues),
            resolved_issues=len(resolved),
            open_issues=len(open_issues),
            cycle_time_stats=stats,
            issues_by_type=by_type,
            linked_prs_count=linked_count,
            traceability_rate=trace_rate,
            findings=findings,
            limitations=[
                (
                    "Issue cycle time includes backlog waiting time "
                    "unless workflow transitions are filtered."
                ),
            ],
        )

    def _load_all_prs(self) -> list[PullRequest]:
        canonical_dir = self.settings.canonical_dir
        if not canonical_dir.exists():
            return []
        prs: list[PullRequest] = []
        for file_path in canonical_dir.glob("*pull_request*.parquet"):
            try:
                from gain.storage.analytics import read_canonical

                prs.extend(read_canonical(file_path))
            except Exception:
                continue
        return prs

    @staticmethod
    def _evaluate_traceability(
        issues: list[CanonicalIssue],
        prs: list[PullRequest],
    ) -> tuple[int, float]:
        """Correlate issue keys with PR metadata."""
        if not issues:
            return 0, 0.0

        linked_issues: set[str] = set()

        for issue in issues:
            # 1. Explicit links in canonical record
            if issue.linked_pr_keys:
                linked_issues.add(issue.key)
                continue

            # 2. Inferred pattern match in PR numbers or repository branch/title
            pattern = re.compile(rf"\b{re.escape(issue.key)}\b", re.IGNORECASE)
            for pr in prs:
                if (issue.key.isdigit() and int(issue.key) == pr.number) or pattern.search(
                    str(pr.number)
                ):
                    linked_issues.add(issue.key)
                    break

        count = len(linked_issues)
        rate = round((count / len(issues)) * 100.0, 1)
        return count, rate
