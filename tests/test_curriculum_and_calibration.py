"""Unit tests for FM.next Domain Curriculum Engineering and Closed-Loop Calibration."""

from pathlib import Path

import pytest

from gain.agent.llm import DeterministicReasoningProvider, LLMGateway
from gain.agent.models import Claim, ClaimType, InvestigationPlan
from gain.config import Settings
from gain.curriculum.taxonomy import DomainCurriculum
from gain.services.calibration import PromptCalibrationService


def test_domain_curriculum_taxonomy_defaults() -> None:
    curriculum = DomainCurriculum.load_default_curriculum()
    assert curriculum.curriculum_version == "1.0.0"

    # Verify core knowledge and skill nodes
    node_ids = set(curriculum.nodes.keys())
    assert "KNOW-FLOW-01" in node_ids
    assert "SKILL-CONFOUND-01" in node_ids
    assert "SKILL-BLOAT-01" in node_ids
    assert "COMP-STABILITY-01" in node_ids

    # Verify bloat defense rules (SE 3.0)
    bloat_node = curriculum.nodes["SKILL-BLOAT-01"]
    assert bloat_node.node_type == "foundational_skill"
    assert any("GAIN-QUAL-003" in r for r in bloat_node.verifiable_rules)
    assert any("GAIN-QUAL-004" in r for r in bloat_node.verifiable_rules)


def test_domain_curriculum_skill_matching_and_compilation() -> None:
    curriculum = DomainCurriculum.load_default_curriculum()

    # Query matching causal attribution & code bloat
    query = "Did AI copilot increase velocity or cause code bloat?"
    matched = curriculum.match_skills(query)
    matched_ids = {n.node_id for n in matched}

    assert "SKILL-CONFOUND-01" in matched_ids
    assert "SKILL-BLOAT-01" in matched_ids

    # Grounding prompt generation
    prompt = curriculum.compile_grounding_prompt(query)
    assert "Authoritative SE Curriculum Grounding" in prompt
    assert "Additive Bias & Code Bloat Mitigation" in prompt
    assert "Verifiable Rule: Tag all non-randomized cohort comparisons" in prompt


def test_prompt_calibration_feedback_recording_and_retrieval(tmp_path: Path) -> None:
    settings = Settings(output_dir=tmp_path / "data")
    service = PromptCalibrationService(settings=settings)

    # 1. Record approved positive briefing (+1)
    ex_pos = service.record_feedback(
        query="Investigate pull request cycle time in firmsoil/gain",
        briefing_text="Median cycle time is 14400.0s with zero-token deterministic calculation.",
        feedback_score=1,
        analyst_id="lead_analyst@firmsoil.com",
        evidence_package_id="ev-100",
    )
    assert ex_pos.exemplar_id.startswith("ex-")
    assert ex_pos.feedback_score == 1

    # 2. Record rejected briefing (-1)
    ex_neg = service.record_feedback(
        query="Did AI make us faster?",
        briefing_text="AI caused a 20% speedup without cohort controls.",
        feedback_score=-1,
        analyst_id="lead_analyst@firmsoil.com",
    )
    assert ex_neg.feedback_score == -1

    # 3. Retrieve positive exemplars for similar query
    retrieved = service.retrieve_positive_exemplars(
        query="What is the pull request cycle time?",
        limit=5,
    )
    assert len(retrieved) == 1
    assert retrieved[0].exemplar_id == ex_pos.exemplar_id
    assert "14400.0s" in retrieved[0].briefing_text


def test_prompt_calibration_prompt_compilation(tmp_path: Path) -> None:
    settings = Settings(output_dir=tmp_path / "data")
    service = PromptCalibrationService(settings=settings)

    # Seed an analyst-approved exemplar
    service.record_feedback(
        query="Analyze PR cycle time bottlenecks",
        briefing_text="Verified exemplar: Cycle time is 18000s, review tax is active.",
        feedback_score=1,
        analyst_id="senior_architect",
    )

    # Compile calibrated prompt for a matching query
    calibrated_prompt = service.compile_calibrated_prompt("PR cycle time analysis")
    assert "Authoritative SE Curriculum Grounding" in calibrated_prompt
    assert "Battle-Tested Exemplar Patterns" in calibrated_prompt
    assert "Verified exemplar: Cycle time is 18000s" in calibrated_prompt


@pytest.mark.anyio
async def test_llm_gateway_integration_with_calibration_service(tmp_path: Path) -> None:
    settings = Settings(output_dir=tmp_path / "data")
    cal_svc = PromptCalibrationService(settings=settings)

    gateway = LLMGateway(
        provider=DeterministicReasoningProvider(),
        calibration_service=cal_svc,
    )

    plan = InvestigationPlan(
        plan_id="plan-cal",
        investigation_id="inv-cal",
        intent="Check cycle time",
        methodology="Curriculum-Test",
        repository="firmsoil/gain",
    )
    claims = [
        Claim(statement="Observed 10 PRs.", classification=ClaimType.OBSERVED),
    ]

    briefing = await gateway.generate_briefing(
        intent="Check cycle time",
        plan=plan,
        claims=claims,
        limitations=[],
    )

    assert "Engineering Intelligence Investigation Briefing" in briefing
    assert "**Repository**: firmsoil/gain" in briefing
