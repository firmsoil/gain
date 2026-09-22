"""Deterministic issue analytics and cross-system traceability service."""

from __future__ import annotations

import re

import structlog
from pydantic import BaseModel, ConfigDict, Field

from gain.config import Settings, get_settings
from gain.mcp.schemas.ai import ClaimClassification
from gain.model.issue import CanonicalIssue
from gain.model.pr import PullRequest
from gain.services.metrics import MetricService
from gain.storage.analytics import scan_canonical
from gain.storage.issues import load_issues_for_project_or_repo
from gain.storage.relationships import RelationshipStore

log = structlog.get_logger(__name__)


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

    def __init__(
        self,
        settings: Settings | None = None,
        relationship_store: RelationshipStore | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.metric_service = MetricService(self.settings)
        self.relationship_store = relationship_store

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
        linked_count, trace_rate = self._evaluate_traceability(
            issues, all_prs, relationship_store=self.relationship_store
        )

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
        lf = scan_canonical(canonical_dir, entity_type="pull_request")
        try:
            df = lf.collect()
            if len(df) == 0:
                return []
            return [PullRequest.model_validate(row) for row in df.to_dicts()]
        except Exception as exc:
            log.warning("load_all_prs_failed", exc_info=exc)
            return []

    @staticmethod
    def _evaluate_traceability(
        issues: list[CanonicalIssue],
        prs: list[PullRequest],
        relationship_store: RelationshipStore | None = None,
    ) -> tuple[int, float]:
        """Correlate issue keys with PR metadata using explicit links, index, or relationships."""
        if not issues:
            return 0, 0.0

        linked_issues: set[str] = set()
        pr_numbers: set[int] = {pr.number for pr in prs}

        for issue in issues:
            # 1. Explicit links in canonical record
            if issue.linked_pr_keys:
                linked_issues.add(issue.key)
                continue

            # 2. Materialized links from RelationshipStore
            if relationship_store and relationship_store.get_linked_prs(issue.key):
                linked_issues.add(issue.key)
                continue

            # 3. Numeric issue key matches PR number (fast O(1) set lookup)
            if issue.key.isdigit() and int(issue.key) in pr_numbers:
                linked_issues.add(issue.key)
                continue

            # 4. Inferred pattern match against distinct PR numbers
            pattern = re.compile(rf"\b{re.escape(issue.key)}\b", re.IGNORECASE)
            for pr_num in pr_numbers:
                if pattern.search(str(pr_num)):
                    linked_issues.add(issue.key)
                    break

        count = len(linked_issues)
        rate = round((count / len(issues)) * 100.0, 1)
        return count, rate
