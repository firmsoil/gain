"""Deterministic metric for post-merge defect rework and fragility (GAIN-QUAL-006).

Evaluates whether code churn exhibits high follow-up defect rework or hotfix frequency
within a 14-day operational window (SE 3.0 Stability and Rework Analysis).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import timedelta

from gain.model.pr import PullRequest


@dataclass(frozen=True)
class DefectReworkObservation:
    """Per-PR observation of follow-up rework and hotfix characteristics."""

    metric_id: str
    metric_version: int
    github_node_id: str
    repository_name_with_owner: str
    pr_number: int
    is_hotfix: bool
    rework_window_days: int
    followup_rework_count: int
    followup_rework_churn: int


class DefectReworkMetric:
    """GAIN-QUAL-006: Deterministic calculation of defect churn and post-merge rework."""

    metric_id = "GAIN-QUAL-006"
    metric_version = 1

    HOTFIX_PATTERN = re.compile(
        r"\b(fix|hotfix|bug|patch|revert|incident|rollback)\b", re.IGNORECASE
    )

    @classmethod
    def observations(
        cls,
        prs: list[PullRequest],
        window_days: int = 14,
    ) -> list[DefectReworkObservation]:
        """Compute defect rework observations across chronologically ordered PRs."""
        sorted_prs = [p for p in prs if p.merged_at is not None]
        sorted_prs.sort(key=lambda p: p.merged_at or p.created_at)

        results: list[DefectReworkObservation] = []
        window_delta = timedelta(days=window_days)

        for i, pr in enumerate(sorted_prs):
            is_hotfix = pr.author_login is not None and bool(
                cls.HOTFIX_PATTERN.search(pr.author_login)
            )
            # Find follow-up PRs within window
            assert pr.merged_at is not None
            end_window = pr.merged_at + window_delta

            followup_count = 0
            followup_churn = 0

            for other in sorted_prs[i + 1 :]:
                if other.merged_at and other.merged_at <= end_window:
                    followup_count += 1
                    followup_churn += (other.additions or 0) + (other.deletions or 0)
                elif other.merged_at and other.merged_at > end_window:
                    break

            results.append(
                DefectReworkObservation(
                    metric_id=cls.metric_id,
                    metric_version=cls.metric_version,
                    github_node_id=pr.github_node_id,
                    repository_name_with_owner=pr.repository_name_with_owner,
                    pr_number=pr.number,
                    is_hotfix=is_hotfix,
                    rework_window_days=window_days,
                    followup_rework_count=followup_count,
                    followup_rework_churn=followup_churn,
                )
            )

        return results

    @classmethod
    def summary(
        cls,
        observations: list[DefectReworkObservation],
        total_prs: int | None = None,
    ) -> dict[str, float | int | None]:
        """Aggregate summary statistics for defect rework and stability."""
        if not observations:
            return {
                "total_observations": 0,
                "total_evaluated_prs": total_prs or 0,
                "hotfix_pr_count": 0,
                "hotfix_percentage": 0.0,
                "total_followup_rework_churn": 0,
                "mean_rework_churn_per_pr": 0.0,
            }

        eval_count = total_prs if total_prs is not None else len(observations)
        hotfix_count = sum(1 for o in observations if o.is_hotfix)
        total_rework_churn = sum(o.followup_rework_churn for o in observations)

        return {
            "total_observations": len(observations),
            "total_evaluated_prs": eval_count,
            "hotfix_pr_count": hotfix_count,
            "hotfix_percentage": (
                round((hotfix_count / eval_count) * 100.0, 2) if eval_count > 0 else 0.0
            ),
            "total_followup_rework_churn": total_rework_churn,
            "mean_rework_churn_per_pr": (
                round(total_rework_churn / eval_count, 1) if eval_count > 0 else 0.0
            ),
        }
