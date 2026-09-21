"""Unit tests for LLMGateway and reasoning synthesis."""

import pytest

from gain.agent.llm import DeterministicReasoningProvider, LLMGateway
from gain.agent.models import Claim, ClaimType, InvestigationPlan


@pytest.mark.anyio
async def test_llm_gateway_deterministic_synthesis() -> None:
    gateway = LLMGateway(provider=DeterministicReasoningProvider())

    plan = InvestigationPlan(
        plan_id="plan-t",
        investigation_id="inv-t",
        intent="What is the cycle time trend?",
        methodology="Cycle-Time Investigation",
        repository="firmsoil/gain",
    )

    claims = [
        Claim(
            statement="Observed 10 pull requests.",
            classification=ClaimType.OBSERVED,
        ),
        Claim(
            statement="Median cycle time is 14400.0s.",
            classification=ClaimType.DERIVED,
        ),
    ]
    limitations = ["Data window is limited to the last 30 days."]

    briefing = await gateway.generate_briefing(
        intent="What is the cycle time trend?",
        plan=plan,
        claims=claims,
        limitations=limitations,
    )

    assert "### Engineering Intelligence Investigation Briefing" in briefing
    assert "**Repository**: firmsoil/gain" in briefing
    assert "- **[Observed]** Observed 10 pull requests." in briefing
    assert "- **[Derived]** Median cycle time is 14400.0s." in briefing
    assert "*Data window is limited to the last 30 days.*" in briefing
