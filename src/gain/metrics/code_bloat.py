"""Deterministic metrics for code bloat and refactoring ratio (SE 3.0 trap detection).

Addresses the 'additive bias' and code bloat pathologies of AI coding assistants
identified in Hassan et al. (2026) 'Towards AI-Native Software Engineering'.
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


# ==============================================================================
# GAIN-QUAL-003: Refactoring vs. Additive Churn Ratio
# ==============================================================================


@dataclass(frozen=True)
class RefactoringRatioObservation:
    """Per-PR observation of refactoring and additive churn distribution."""

    metric_id: str
    metric_version: int
    github_node_id: str
    repository_name_with_owner: str
    pr_number: int
    additions: int
    deletions: int
    total_churn: int
    refactoring_ratio: float
    additive_ratio: float
    is_pure_addition: bool


class RefactoringRatioMetric:
    """GAIN-QUAL-003: Deterministic computation of refactoring vs additive churn ratio.

    Formula:
        refactoring_ratio = deletions / (additions + deletions)
        additive_ratio = additions / (additions + deletions)
    """

    metric_id = "GAIN-QUAL-003"
    metric_version = 1

    @classmethod
    def observations(cls, prs: list[PullRequest]) -> list[RefactoringRatioObservation]:
        output: list[RefactoringRatioObservation] = []
        for pr in prs:
            adds = pr.additions or 0
            dels = pr.deletions or 0
            churn = adds + dels
            if churn <= 0:
                continue

            refactor_ratio = dels / churn
            additive_ratio = adds / churn
            is_pure_add = adds > 0 and dels == 0

            output.append(
                RefactoringRatioObservation(
                    metric_id=cls.metric_id,
                    metric_version=cls.metric_version,
                    github_node_id=pr.github_node_id,
                    repository_name_with_owner=pr.repository_name_with_owner,
                    pr_number=pr.number,
                    additions=adds,
                    deletions=dels,
                    total_churn=churn,
                    refactoring_ratio=round(refactor_ratio, 4),
                    additive_ratio=round(additive_ratio, 4),
                    is_pure_addition=is_pure_add,
                )
            )
        return output

    @classmethod
    def summary(
        cls,
        observations: list[RefactoringRatioObservation],
        total_prs: int | None = None,
    ) -> dict[str, float | int | None]:
        refactor_values = sorted(item.refactoring_ratio for item in observations)
        additive_values = sorted(item.additive_ratio for item in observations)
        count = len(observations)

        total_adds = sum(item.additions for item in observations)
        total_dels = sum(item.deletions for item in observations)
        total_churn = total_adds + total_dels
        pure_add_count = sum(1 for item in observations if item.is_pure_addition)

        agg_refactor = (total_dels / total_churn) if total_churn > 0 else 0.0
        agg_additive = (total_adds / total_churn) if total_churn > 0 else 0.0
        pure_add_pct = (pure_add_count / count * 100.0) if count > 0 else 0.0

        return {
            "count": count,
            "total_evaluated": total_prs if total_prs is not None else count,
            "total_additions": total_adds,
            "total_deletions": total_dels,
            "total_churn": total_churn,
            "aggregate_refactoring_ratio": round(agg_refactor, 4),
            "aggregate_additive_ratio": round(agg_additive, 4),
            "pure_addition_count": pure_add_count,
            "pure_addition_percentage": round(pure_add_pct, 2),
            "p50_refactoring_ratio": _percentile(refactor_values, 0.50),
            "p75_refactoring_ratio": _percentile(refactor_values, 0.75),
            "p90_refactoring_ratio": _percentile(refactor_values, 0.90),
            "mean_refactoring_ratio": (
                round(mean(refactor_values), 4) if refactor_values else None
            ),
            "p50_additive_ratio": _percentile(additive_values, 0.50),
            "mean_additive_ratio": round(mean(additive_values), 4) if additive_values else None,
        }


# ==============================================================================
# GAIN-QUAL-004: Code Bloat & Expansion Index
# ==============================================================================


@dataclass(frozen=True)
class CodeBloatObservation:
    """Per-PR observation of code expansion density per changed file."""

    metric_id: str
    metric_version: int
    github_node_id: str
    repository_name_with_owner: str
    pr_number: int
    additions: int
    deletions: int
    changed_files: int
    net_additions: int
    net_additions_per_file: float
    churn_per_file: float
    is_bloat_flagged: bool


class CodeBloatMetric:
    """GAIN-QUAL-004: Deterministic computation of code bloat density.

    Formula:
        net_additions = max(0, additions - deletions)
        net_additions_per_file = net_additions / max(1, changed_files)
        churn_per_file = (additions + deletions) / max(1, changed_files)
    """

    metric_id = "GAIN-QUAL-004"
    metric_version = 1

    @classmethod
    def observations(
        cls,
        prs: list[PullRequest],
        bloat_expansion_threshold: float = 100.0,
    ) -> list[CodeBloatObservation]:
        output: list[CodeBloatObservation] = []
        for pr in prs:
            adds = pr.additions or 0
            dels = pr.deletions or 0
            files = max(1, pr.changed_files or 1)
            churn = adds + dels
            if churn <= 0:
                continue

            net_adds = max(0, adds - dels)
            net_per_file = net_adds / files
            churn_per_file = churn / files
            is_bloated = net_per_file >= bloat_expansion_threshold

            output.append(
                CodeBloatObservation(
                    metric_id=cls.metric_id,
                    metric_version=cls.metric_version,
                    github_node_id=pr.github_node_id,
                    repository_name_with_owner=pr.repository_name_with_owner,
                    pr_number=pr.number,
                    additions=adds,
                    deletions=dels,
                    changed_files=files,
                    net_additions=net_adds,
                    net_additions_per_file=round(net_per_file, 2),
                    churn_per_file=round(churn_per_file, 2),
                    is_bloat_flagged=is_bloated,
                )
            )
        return output

    @classmethod
    def summary(
        cls,
        observations: list[CodeBloatObservation],
        total_prs: int | None = None,
    ) -> dict[str, float | int | None]:
        net_per_file_values = sorted(item.net_additions_per_file for item in observations)
        churn_per_file_values = sorted(item.churn_per_file for item in observations)
        count = len(observations)

        total_net_adds = sum(item.net_additions for item in observations)
        total_files = sum(item.changed_files for item in observations)
        bloat_flag_count = sum(1 for item in observations if item.is_bloat_flagged)

        agg_net_per_file = (total_net_adds / total_files) if total_files > 0 else 0.0
        bloat_pct = (bloat_flag_count / count * 100.0) if count > 0 else 0.0

        return {
            "count": count,
            "total_evaluated": total_prs if total_prs is not None else count,
            "total_net_additions": total_net_adds,
            "total_changed_files": total_files,
            "aggregate_net_additions_per_file": round(agg_net_per_file, 2),
            "bloat_flag_count": bloat_flag_count,
            "bloat_flag_percentage": round(bloat_pct, 2),
            "p50_net_additions_per_file": _percentile(net_per_file_values, 0.50),
            "p75_net_additions_per_file": _percentile(net_per_file_values, 0.75),
            "p90_net_additions_per_file": _percentile(net_per_file_values, 0.90),
            "mean_net_additions_per_file": (
                round(mean(net_per_file_values), 2) if net_per_file_values else None
            ),
            "p50_churn_per_file": _percentile(churn_per_file_values, 0.50),
            "mean_churn_per_file": (
                round(mean(churn_per_file_values), 2) if churn_per_file_values else None
            ),
        }
