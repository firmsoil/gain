"""Evidence Synthesizer: Constructs auditable evidence packages and classifies claims."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import structlog

from gain.agent.models import Claim, ClaimType, InvestigationPlan, PlanStepStatus
from gain.services.evidence import EvidencePackage, EvidenceService

logger = structlog.get_logger(__name__)


class EvidenceSynthesizer:
    """Synthesizes step execution results into an immutable EvidencePackage and tagged Claims."""

    def __init__(self, evidence_service: EvidenceService | None = None) -> None:
        self.evidence_service = evidence_service or EvidenceService()

    def synthesize(
        self,
        plan: InvestigationPlan,
        investigation_id: str,
    ) -> tuple[list[Claim], str | None, list[str]]:
        """Extract claims, assemble evidence package, and detect limitations."""
        claims: list[Claim] = []
        limitations: list[str] = []
        supporting_artifacts: dict[str, Any] = {}

        for step in plan.steps:
            if step.status != PlanStepStatus.COMPLETED or not step.output:
                if step.status == PlanStepStatus.FAILED:
                    limitations.append(
                        f"Step '{step.step_id}' ({step.tool_name}) failed: {step.error}"
                    )
                continue

            tool_name = step.tool_name
            out = step.output
            supporting_artifacts[f"{step.step_id}_{tool_name}"] = out

            if tool_name == "query_engineering_metrics":
                self._extract_metric_claims(out, claims, limitations)
            elif tool_name == "compare_cohorts":
                self._extract_cohort_claims(out, claims, limitations)
            elif tool_name == "analyze_ai_impact":
                self._extract_ai_impact_claims(out, claims, limitations)
            elif tool_name == "calculate_ai_roi":
                self._extract_ai_roi_claims(out, claims, limitations)
            elif tool_name == "get_dora_metrics":
                self._extract_dora_claims(out, claims, limitations)
            elif tool_name == "get_data_quality":
                self._extract_quality_claims(out, claims, limitations)
            elif tool_name == "get_pull_request_details":
                self._extract_github_context_claims(out, claims, limitations)

        # Build durable EvidencePackage
        package_id = f"ev-{uuid4().hex[:8]}"
        evidence_pkg = EvidencePackage(
            evidence_id=package_id,
            claim=claims[0].statement if claims else "Investigation finding",
            claim_classification=claims[0].classification.value if claims else "Unknown",
            metric_id=claims[0].metric_id or "GAIN-PR-001" if claims else "GAIN-PR-001",
            metric_version=1,
            population_count=len(claims),
            time_window=plan.created_at.isoformat(),
            data_freshness_utc=plan.created_at.isoformat(),
            statistical_method="deterministic_canonical_metrics",
            assumptions=["Metrics derived from deterministic canonical calculations"],
            limitations=limitations,
            confidence_level="High" if not limitations else "Medium",
            source_references=[f"plan:{plan.plan_id}", f"repo:{plan.repository}"],
            supporting_artifacts=[f"{s.step_id}:{s.tool_name}" for s in plan.steps],
        )

        try:
            self.evidence_service.store_evidence(evidence_pkg)
            logger.info(
                "evidence_package_synthesized", package_id=package_id, claim_count=len(claims)
            )
            return claims, package_id, limitations
        except Exception as exc:
            logger.warning("evidence_persistence_warning", error=str(exc))
            return claims, package_id, limitations

    def _extract_metric_claims(
        self, out: dict[str, Any], claims: list[Claim], limitations: list[str]
    ) -> None:
        metric_id = out.get("metric_id", "GAIN-PR-001")
        summary = out.get("summary", {})
        count = summary.get("count", 0)

        # Claim 1: Observed count
        claims.append(
            Claim(
                statement=(
                    f"Observed {count} pull requests in target population for metric {metric_id}."
                ),
                classification=ClaimType.OBSERVED,
                confidence=1.0,
                metric_id=metric_id,
                source_refs=[f"repo:{out.get('repository')}"],
            )
        )

        # Claim 2: Derived percentiles
        if count > 0:
            p50 = summary.get("p50_seconds", 0.0)
            p90 = summary.get("p90_seconds", 0.0)
            claims.append(
                Claim(
                    statement=(
                        f"Calculated PR cycle-time distribution: median (p50) is {p50:.1f}s, "
                        f"90th percentile (p90) is {p90:.1f}s."
                    ),
                    classification=ClaimType.DERIVED,
                    confidence=1.0,
                    metric_id=metric_id,
                    source_refs=[f"repo:{out.get('repository')}"],
                )
            )
        else:
            limitations.append(f"No completed PR events observed for metric {metric_id}.")

    def _extract_cohort_claims(
        self, out: dict[str, Any], claims: list[Claim], limitations: list[str]
    ) -> None:
        c_a = out.get("cohort_a_name", "cohort_a")
        c_b = out.get("cohort_b_name", "cohort_b")
        deltas = out.get("deltas", {})
        p50_delta = deltas.get("delta_p50_seconds", 0.0)

        claims.append(
            Claim(
                statement=(
                    f"Observed median cycle-time delta of {p50_delta:+.1f}s between '{c_a}' "
                    f"and '{c_b}'. This reflects an associated difference, not causal attribution."
                ),
                classification=ClaimType.ASSOCIATED,
                confidence=0.9,
                metric_id=out.get("metric_id"),
                notes=(
                    "Confounding variables such as PR size and review count have not been isolated."
                ),
            )
        )

    def _extract_ai_impact_claims(
        self, out: dict[str, Any], claims: list[Claim], limitations: list[str]
    ) -> None:
        status_val = str(out.get("status", "")).lower()
        if "insufficient_data" in status_val:
            limitations.append(
                "Authoritative AI telemetry (e.g. Copilot seat activity, acceptance rates) "
                "is missing. AI attribution cannot be asserted."
            )
            claims.append(
                Claim(
                    statement=(
                        "Direct AI delivery attribution is unsupported due to missing "
                        "author-level AI telemetry."
                    ),
                    classification=ClaimType.UNKNOWN,
                    confidence=1.0,
                    notes=(
                        "Per Master Spec Section 2, inference from generic PR characteristics "
                        "is prohibited."
                    ),
                )
            )

    def _extract_ai_roi_claims(
        self, out: dict[str, Any], claims: list[Claim], limitations: list[str]
    ) -> None:
        status_val = str(out.get("status", "")).lower()
        if "available" in status_val:
            roi_pct = float(out.get("roi_percentage", 0.0) or 0.0)
            net = float(out.get("net_benefit", 0.0) or 0.0)
            unc = out.get("uncertainty_range", {})
            min_roi = float(unc.get("min_roi_percentage", 0.0) or 0.0)
            max_roi = float(unc.get("max_roi_percentage", 0.0) or 0.0)

            claims.append(
                Claim(
                    statement=(
                        f"Modeled expected AI developer ROI is projected at {roi_pct:.1f}% "
                        f"(net economic benefit: ${net:,.2f}) based on parameterized benchmark "
                        "assumptions."
                    ),
                    classification=ClaimType.MODELED,
                    confidence=0.85,
                    notes=(
                        f"Sensitivity uncertainty range: conservative {min_roi:.1f}% to "
                        f"optimistic {max_roi:.1f}%."
                    ),
                )
            )
            for assump in out.get("assumptions", [])[:2]:
                claims.append(
                    Claim(
                        statement=f"Assumed parameter: {assump}",
                        classification=ClaimType.ASSUMED,
                        confidence=1.0,
                    )
                )

    def _extract_quality_claims(
        self, out: dict[str, Any], claims: list[Claim], limitations: list[str]
    ) -> None:
        validity = out.get("validity_score", 1.0)
        freshness = out.get("freshness_status", "fresh")
        claims.append(
            Claim(
                statement=(
                    f"Dataset validity score is {validity * 100:.1f}%; "
                    f"freshness status is '{freshness}'."
                ),
                classification=ClaimType.DERIVED,
                confidence=1.0,
            )
        )
        if validity < 0.8:
            limitations.append(
                f"Dataset validity ({validity:.2f}) is below optimal threshold (0.80)."
            )

    def _extract_github_context_claims(
        self, out: dict[str, Any], claims: list[Claim], limitations: list[str]
    ) -> None:
        if out.get("degraded"):
            limitations.append("Live GitHub operational context was degraded or unavailable.")
            return

        prs = out.get("pull_requests", [])
        if prs:
            titles = [f"#{pr.get('number')}: {pr.get('title')}" for pr in prs[:2]]
            claims.append(
                Claim(
                    statement=f"Sampled live PR context: {'; '.join(titles)}.",
                    classification=ClaimType.OBSERVED,
                    confidence=1.0,
                )
            )

    def _extract_dora_claims(
        self, out: dict[str, Any], claims: list[Claim], limitations: list[str]
    ) -> None:
        status = out.get("status")
        if status == "insufficient_data":
            limitations.append("DORA metrics unavailable due to missing deployment telemetry.")
            for dep in out.get("missing_dependencies", []):
                limitations.append(f"Missing dependency: {dep}")
            claims.append(
                Claim(
                    statement=(
                        "DORA delivery metrics cannot be calculated: "
                        "production deployment telemetry is missing."
                    ),
                    classification=ClaimType.UNKNOWN,
                    confidence=1.0,
                )
            )
            return

        dep_freq = out.get("deployment_frequency", {})
        cfr = out.get("change_fail_rate", {})
        lead_time = out.get("change_lead_time", {})

        if dep_freq.get("value") is not None:
            claims.append(
                Claim(
                    statement=(
                        f"Deployment frequency is {dep_freq['value']} "
                        f"{dep_freq.get('unit', 'deployments/week')}."
                    ),
                    classification=ClaimType.DERIVED,
                    metric_id="GAIN-DORA-002",
                    confidence=1.0,
                )
            )
        if cfr.get("value") is not None:
            claims.append(
                Claim(
                    statement=(
                        f"Change failure rate is {cfr['value']}% for production deployments."
                    ),
                    classification=ClaimType.DERIVED,
                    metric_id="GAIN-DORA-003",
                    confidence=1.0,
                )
            )
        if lead_time.get("value") is not None:
            claims.append(
                Claim(
                    statement=(
                        f"Median commit-to-deployment lead time is {lead_time['value']} "
                        f"{lead_time.get('unit', 'seconds')}."
                    ),
                    classification=ClaimType.DERIVED,
                    metric_id="GAIN-DORA-001",
                    confidence=1.0,
                )
            )
