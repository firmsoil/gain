"""Unit tests for EvidenceSynthesizer and claim classification."""

from pathlib import Path

from gain.agent.models import ClaimType, InvestigationPlan, PlanStep, PlanStepStatus
from gain.agent.synthesizer import EvidenceSynthesizer
from gain.services.evidence import EvidenceService


def test_synthesizer_classifies_metric_claims(tmp_path: Path) -> None:
    from gain.config import Settings

    svc = EvidenceService(settings=Settings(output_dir=tmp_path))
    synthesizer = EvidenceSynthesizer(evidence_service=svc)

    plan = InvestigationPlan(
        plan_id="plan-1",
        investigation_id="inv-1",
        intent="Evaluate cycle time",
        methodology="Metric Investigation",
        repository="firmsoil/gain",
        steps=[
            PlanStep(
                step_id="step-1",
                description="Query metric",
                tool_name="query_engineering_metrics",
                target_system="gain_mcp",
                status=PlanStepStatus.COMPLETED,
                output={
                    "metric_id": "GAIN-PR-001",
                    "repository": "firmsoil/gain",
                    "summary": {
                        "count": 42,
                        "p50_seconds": 3600.0,
                        "p90_seconds": 18000.0,
                    },
                },
            )
        ],
    )

    claims, evidence_id, limitations = synthesizer.synthesize(plan, "inv-1")

    assert evidence_id is not None
    assert len(claims) == 2

    # Claim 1: Observed count
    assert claims[0].classification == ClaimType.OBSERVED
    assert "42 pull requests" in claims[0].statement

    # Claim 2: Derived percentiles
    assert claims[1].classification == ClaimType.DERIVED
    assert "median (p50) is 3600.0s" in claims[1].statement


def test_synthesizer_classifies_ai_gap_as_unknown(tmp_path: Path) -> None:
    from gain.config import Settings

    svc = EvidenceService(settings=Settings(output_dir=tmp_path))
    synthesizer = EvidenceSynthesizer(evidence_service=svc)

    plan = InvestigationPlan(
        plan_id="plan-ai",
        investigation_id="inv-ai",
        intent="Check AI impact",
        methodology="AI Attribution",
        repository="firmsoil/gain",
        steps=[
            PlanStep(
                step_id="step-1",
                description="AI Impact",
                tool_name="analyze_ai_impact",
                target_system="gain_mcp",
                status=PlanStepStatus.COMPLETED,
                output={"status": "insufficient_data"},
            )
        ],
    )

    claims, evidence_id, limitations = synthesizer.synthesize(plan, "inv-ai")

    assert len(claims) == 1
    assert claims[0].classification == ClaimType.UNKNOWN
    assert "unsupported due to missing author-level AI telemetry" in claims[0].statement
    assert any("Authoritative AI telemetry" in lim for lim in limitations)
