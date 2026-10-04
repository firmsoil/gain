"""Deterministic SE 3.0 Quality Gate engine for CI/CD pipelines.

Inspects GAIN scorecard JSON telemetry and validates code health against
strict numerical thresholds without any non-deterministic or LLM reasoning.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class QualityGateResult:
    """Outcome of evaluating deterministic quality gate thresholds."""

    passed: bool
    violations: list[str]
    bloat_percentage: float
    max_bloat_threshold: float
    refactoring_ratio: float
    min_refactoring_threshold: float
    friction_percentage: float
    max_friction_threshold: float
    hotfix_percentage: float
    max_hotfix_threshold: float
    total_evaluated_prs: int


def evaluate_quality_gate(
    scorecard: dict[str, Any],
    max_bloat_pct: float = 25.0,
    min_refactor_ratio: float = 0.10,
    max_friction_pct: float = 30.0,
    max_hotfix_pct: float = 25.0,
    min_sample_size: int = 5,
) -> QualityGateResult:
    """Evaluate deterministic quality gate rules against a GAIN scorecard."""
    violations: list[str] = []

    telemetry = scorecard.get("telemetry_overview", {})
    quality = scorecard.get("code_quality_and_bloat", {})
    stability = scorecard.get("verification_and_stability", {})

    total_prs = int(telemetry.get("total_prs_evaluated") or 0)
    bloat_pct = float(quality.get("bloat_flagged_percentage") or 0.0)
    refactor_ratio = float(quality.get("aggregate_refactoring_ratio") or 0.0)
    pure_adds_pct = float(quality.get("pure_additions_percentage") or 0.0)
    friction_pct = float(stability.get("high_friction_review_pct") or 0.0)
    hotfix_pct = float(stability.get("hotfix_pr_percentage") or 0.0)

    # 1. Code Bloat Index Gate (GAIN-QUAL-004)
    if bloat_pct > max_bloat_pct:
        violations.append(
            f"Code Bloat Gate (GAIN-QUAL-004): {bloat_pct:.1f}% of files flagged "
            f"(threshold <= {max_bloat_pct:.1f}%)"
        )

    # 2. Refactoring vs Additive Bias Gate (GAIN-QUAL-003)
    excessive_pure_adds = pure_adds_pct > 85.0
    if total_prs >= min_sample_size and refactor_ratio < min_refactor_ratio and excessive_pure_adds:
        violations.append(
            f"Additive Bias Gate (GAIN-QUAL-003): Refactoring ratio is {refactor_ratio:.1%} "
            f"with {pure_adds_pct:.1f}% pure additions (threshold >= {min_refactor_ratio:.1%})"
        )

    # 3. Review Queue Latency & Verification Tax Gate (GAIN-QUAL-005)
    if total_prs >= min_sample_size and friction_pct > max_friction_pct:
        violations.append(
            f"Verification Tax Gate (GAIN-QUAL-005): {friction_pct:.1f}% of PR reviews linger >48h "
            f"(threshold <= {max_friction_pct:.1f}%)"
        )

    # 4. Defect Rework & Fragility Gate (GAIN-QUAL-006)
    if total_prs >= min_sample_size and hotfix_pct > max_hotfix_pct:
        violations.append(
            f"Defect Rework Gate (GAIN-QUAL-006): {hotfix_pct:.1f}% hotfix churn in 14-day window "
            f"(threshold <= {max_hotfix_pct:.1f}%)"
        )

    return QualityGateResult(
        passed=len(violations) == 0,
        violations=violations,
        bloat_percentage=bloat_pct,
        max_bloat_threshold=max_bloat_pct,
        refactoring_ratio=refactor_ratio,
        min_refactoring_threshold=min_refactor_ratio,
        friction_percentage=friction_pct,
        max_friction_threshold=max_friction_pct,
        hotfix_percentage=hotfix_pct,
        max_hotfix_threshold=max_hotfix_pct,
        total_evaluated_prs=total_prs,
    )
