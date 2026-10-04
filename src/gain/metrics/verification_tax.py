"""Deterministic metric for Verification Tax and review bottlenecks (GAIN-QUAL-005).

Measures whether code review and verification latency outstrips generation speedups,
quantifying the 'Verification Tax' identified in Google Cloud DORA (2026) and Hassan et al. (2026).
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean

from gain.model.pr import PullRequest


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    rank = q * (len(values) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(values) - 1)
    fraction = rank - lower
    return values[lower] + fraction * (values[upper] - values[lower])


@dataclass(frozen=True)
class VerificationTaxObservation:
    """Per-PR observation of code review duration and verification friction."""

    metric_id: str
    metric_version: int
    github_node_id: str
    repository_name_with_owner: str
    pr_number: int
    review_latency_hours: float
    total_churn: int
    verification_tax_ratio: float
    is_high_friction: bool


class VerificationTaxMetric:
    """GAIN-QUAL-005: Deterministic evaluation of review friction and verification tax.

    Formula:
        review_latency_hours = (merged_at - created_at) in hours
        verification_tax_ratio = review_latency_hours / max(1.0, total_churn / 100.0)
    """

    metric_id = "GAIN-QUAL-005"
    metric_version = 1

    @classmethod
    def observations(
        cls,
        prs: list[PullRequest],
        high_friction_threshold_hours: float = 48.0,
    ) -> list[VerificationTaxObservation]:
        """Compute verification tax observations for merged pull requests."""
        results: list[VerificationTaxObservation] = []
        for pr in prs:
            if not pr.merged_at or not pr.created_at:
                continue

            latency_secs = max(0.0, (pr.merged_at - pr.created_at).total_seconds())
            latency_hours = round(latency_secs / 3600.0, 2)
            churn = (pr.additions or 0) + (pr.deletions or 0)
            churn_hundreds = max(1.0, churn / 100.0)
            tax_ratio = round(latency_hours / churn_hundreds, 3)

            results.append(
                VerificationTaxObservation(
                    metric_id=cls.metric_id,
                    metric_version=cls.metric_version,
                    github_node_id=pr.github_node_id,
                    repository_name_with_owner=pr.repository_name_with_owner,
                    pr_number=pr.number,
                    review_latency_hours=latency_hours,
                    total_churn=churn,
                    verification_tax_ratio=tax_ratio,
                    is_high_friction=latency_hours >= high_friction_threshold_hours,
                )
            )
        return results

    @classmethod
    def summary(
        cls,
        observations: list[VerificationTaxObservation],
        total_prs: int | None = None,
    ) -> dict[str, float | int | None]:
        """Aggregate summary statistics and percentiles for verification tax."""
        if not observations:
            return {
                "total_observations": 0,
                "total_evaluated_prs": total_prs or 0,
                "p50_latency_hours": None,
                "p75_latency_hours": None,
                "p90_latency_hours": None,
                "mean_latency_hours": None,
                "mean_verification_tax_ratio": None,
                "high_friction_pr_count": 0,
                "high_friction_percentage": 0.0,
            }

        latencies = sorted(o.review_latency_hours for o in observations)
        tax_ratios = [o.verification_tax_ratio for o in observations]
        high_friction = sum(1 for o in observations if o.is_high_friction)
        eval_count = total_prs if total_prs is not None else len(observations)

        return {
            "total_observations": len(observations),
            "total_evaluated_prs": eval_count,
            "p50_latency_hours": _percentile(latencies, 0.50),
            "p75_latency_hours": _percentile(latencies, 0.75),
            "p90_latency_hours": _percentile(latencies, 0.90),
            "mean_latency_hours": round(mean(latencies), 2),
            "mean_verification_tax_ratio": round(mean(tax_ratios), 3),
            "high_friction_pr_count": high_friction,
            "high_friction_percentage": (
                round((high_friction / eval_count) * 100.0, 2) if eval_count > 0 else 0.0
            ),
        }
