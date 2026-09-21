"""Deterministic AI Impact analytical service for cohort evaluation and confounder isolation."""

from __future__ import annotations

from typing import Any

import structlog

from gain.config import Settings, get_settings
from gain.mcp.schemas.ai import AIImpactResult, ClaimClassification
from gain.metrics.cycle_time import CycleTimeMetric
from gain.model.pr import PullRequest
from gain.services.metrics import MetricService
from gain.storage.ai_telemetry import load_ai_telemetry_for_repo

logger = structlog.get_logger(__name__)


class AIImpactService:
    """Evaluates empirical delivery flow changes between AI-assisted and baseline cohorts."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.metric_service = MetricService(self.settings)

    def analyze_impact(
        self,
        repository: str,
        cohort_definition: dict[str, Any] | None = None,
        comparison_cohort: dict[str, Any] | None = None,
    ) -> AIImpactResult:
        """Deterministically compare AI-active author PRs against baseline PRs."""
        telemetry_records = load_ai_telemetry_for_repo(
            repo=repository, canonical_dir=self.settings.canonical_dir
        )

        # 1. Check for authoritative developer telemetry
        if not telemetry_records:
            logger.info("ai_impact_insufficient_data", repository=repository)
            return AIImpactResult(
                status="insufficient_data",
                classification=ClaimClassification.UNKNOWN,
                attribution_source=None,
                attribution_method=None,
                cohort_definition=cohort_definition or {"repository": repository},
                comparison_cohort=comparison_cohort,
                confidence_level="Low",
                limitations=[
                    (
                        "Authoritative AI adoption data (e.g. Copilot API) is not yet ingested "
                        "into GAIN canonical storage."
                    ),
                    (
                        "PR volume or velocity must not be used as a proxy for AI assistance "
                        "without verified author-level telemetry."
                    ),
                ],
                findings=[],
                missing_dependencies=[
                    "GitHub Copilot Telemetry / AI Attribution Dataset",
                    "Developer Tooling Usage Logs",
                ],
            )

        # 2. Extract active AI authors
        ai_developer_logins = {r.developer_id for r in telemetry_records if r.is_ai_active}
        total_suggestions = sum(r.suggestions_count for r in telemetry_records)
        total_acceptances = sum(r.acceptances_count for r in telemetry_records)
        overall_acceptance_rate = (
            round(total_acceptances / total_suggestions, 4) if total_suggestions > 0 else 0.0
        )

        # 3. Partition canonical PRs for repository
        all_prs = self.metric_service._load_canonical_prs(repository=repository)
        ai_prs: list[PullRequest] = []
        baseline_prs: list[PullRequest] = []

        for pr in all_prs:
            if pr.author_login and pr.author_login in ai_developer_logins:
                ai_prs.append(pr)
            else:
                baseline_prs.append(pr)

        # 4. Calculate deterministic metrics for both cohorts
        ai_obs = CycleTimeMetric.observations(ai_prs)
        baseline_obs = CycleTimeMetric.observations(baseline_prs)

        ai_summary = CycleTimeMetric.summary(ai_obs, total_prs=len(ai_prs))
        baseline_summary = CycleTimeMetric.summary(baseline_obs, total_prs=len(baseline_prs))

        ai_p50 = float(ai_summary.get("p50_seconds") or 0.0)
        base_p50 = float(baseline_summary.get("p50_seconds") or 0.0)
        delta_p50 = round(ai_p50 - base_p50, 1)

        # 5. Confounder analysis: PR size
        ai_avg_lines = sum((p.additions or 0) + (p.deletions or 0) for p in ai_prs) / max(
            1, len(ai_prs)
        )
        base_avg_lines = sum((p.additions or 0) + (p.deletions or 0) for p in baseline_prs) / max(
            1, len(baseline_prs)
        )
        size_confounder = abs(ai_avg_lines - base_avg_lines) > (0.25 * max(1.0, base_avg_lines))

        findings = [
            (
                f"Authoritative AI telemetry identified {len(ai_developer_logins)} "
                f"active AI developers with {overall_acceptance_rate * 100:.1f}% "
                "code acceptance rate."
            ),
            (
                f"Evaluated {len(ai_prs)} AI-cohort PRs (p50: {ai_p50:.1f}s) vs "
                f"{len(baseline_prs)} baseline PRs (p50: {base_p50:.1f}s). "
                f"Delta: {delta_p50:+.1f}s."
            ),
        ]

        limitations = [
            (
                "Cohort differences reflect observed statistical association, "
                "not randomized causal proof."
            ),
        ]
        if size_confounder:
            limitations.append(
                f"PR size disparity detected (AI cohort avg: {ai_avg_lines:.0f} lines "
                f"vs baseline: {base_avg_lines:.0f} lines); "
                "PR size is an active confounding factor."
            )

        return AIImpactResult(
            status="available",
            classification=ClaimClassification.ASSOCIATED,
            attribution_source="GAIN Canonical AI Telemetry Store",
            attribution_method="Developer-level adoption cohort comparison",
            cohort_definition={
                "repository": repository,
                "ai_active_developers": len(ai_developer_logins),
                "ai_prs_evaluated": len(ai_prs),
            },
            comparison_cohort={
                "repository": repository,
                "baseline_prs_evaluated": len(baseline_prs),
            },
            confidence_level="Medium" if not size_confounder else "Low",
            limitations=limitations,
            findings=findings,
            missing_dependencies=[],
        )
