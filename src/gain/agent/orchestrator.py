"""Engineering Intelligence Agent Orchestrator: Governed investigation lifecycle."""

from __future__ import annotations

import time
from typing import Any

import structlog

from gain.agent.gateway import AgentGateway
from gain.agent.llm import LLMGateway
from gain.agent.models import AgentResponse, InvestigationContext, PlanStepStatus
from gain.agent.planner import InvestigationPlanner
from gain.agent.policy import PolicyGuard
from gain.agent.router import ToolRouter
from gain.agent.synthesizer import EvidenceSynthesizer

logger = structlog.get_logger(__name__)


class EngineeringIntelligenceAgent:
    """Core autonomous runtime for engineering intelligence investigations."""

    def __init__(
        self,
        gateway: AgentGateway | None = None,
        planner: InvestigationPlanner | None = None,
        policy_guard: PolicyGuard | None = None,
        tool_router: ToolRouter | None = None,
        synthesizer: EvidenceSynthesizer | None = None,
        llm_gateway: LLMGateway | None = None,
    ) -> None:
        self.gateway = gateway or AgentGateway()
        self.planner = planner or InvestigationPlanner()
        self.policy_guard = policy_guard or PolicyGuard()
        self.tool_router = tool_router or ToolRouter()
        self.synthesizer = synthesizer or EvidenceSynthesizer()
        self.llm_gateway = llm_gateway or LLMGateway()

    async def investigate(
        self,
        query: str,
        context: InvestigationContext | None = None,
        default_repo: str = "firmsoil/gain",
    ) -> AgentResponse:
        """Execute a full, governed investigation lifecycle."""
        ctx = context or self.gateway.create_context()
        audit_events: list[dict[str, Any]] = []

        logger.info(
            "agent_investigation_started", query=query, investigation_id=ctx.investigation_id
        )
        audit_events.append(
            {
                "event": "investigation_started",
                "request_id": ctx.request_id,
                "investigation_id": ctx.investigation_id,
                "query": query,
            }
        )

        # 1. Plan creation & budget verification
        plan = self.planner.create_plan(query, ctx, default_repo=default_repo)
        self.gateway.validate_plan_budget(len(plan.steps))
        audit_events.append(
            {
                "event": "plan_created",
                "plan_id": plan.plan_id,
                "step_count": len(plan.steps),
                "methodology": plan.methodology,
            }
        )

        # 2. Step execution loop
        for step in plan.steps:
            step.status = PlanStepStatus.RUNNING
            t_start = time.perf_counter()

            try:
                # Security policy enforcement
                self.policy_guard.validate_tool_execution(
                    tool_name=step.tool_name,
                    target_system=step.target_system,
                    context=ctx,
                )

                # Tool dispatch through router
                raw_output = await self.tool_router.route_tool_call(
                    target_system=step.target_system,
                    tool_name=step.tool_name,
                    arguments=step.arguments,
                )

                # Prompt injection defense & untrusted text sanitization
                step.output = self.policy_guard.sanitize_tool_output(raw_output)
                step.status = PlanStepStatus.COMPLETED
                step.duration_ms = (time.perf_counter() - t_start) * 1000.0

                audit_events.append(
                    {
                        "event": "step_completed",
                        "step_id": step.step_id,
                        "tool": step.tool_name,
                        "system": step.target_system,
                        "duration_ms": step.duration_ms,
                    }
                )

            except Exception as exc:
                step.status = PlanStepStatus.FAILED
                step.error = str(exc)
                step.duration_ms = (time.perf_counter() - t_start) * 1000.0
                logger.error(
                    "agent_step_execution_failed",
                    step_id=step.step_id,
                    tool=step.tool_name,
                    error=str(exc),
                )
                audit_events.append(
                    {
                        "event": "step_failed",
                        "step_id": step.step_id,
                        "tool": step.tool_name,
                        "error": str(exc),
                    }
                )

        # 3. Evidence synthesis & claim classification
        claims, evidence_pkg_id, limitations = self.synthesizer.synthesize(
            plan=plan,
            investigation_id=ctx.investigation_id,
        )
        audit_events.append(
            {
                "event": "evidence_synthesized",
                "evidence_package_id": evidence_pkg_id,
                "claim_count": len(claims),
            }
        )

        # 4. Constrained LLM reasoning briefing
        briefing = await self.llm_gateway.generate_briefing(
            intent=query,
            plan=plan,
            claims=claims,
            limitations=limitations,
        )
        audit_events.append(
            {
                "event": "briefing_generated",
                "evidence_package_id": evidence_pkg_id,
            }
        )

        logger.info(
            "agent_investigation_completed",
            investigation_id=ctx.investigation_id,
            claim_count=len(claims),
            evidence_id=evidence_pkg_id,
        )

        return AgentResponse(
            investigation_id=ctx.investigation_id,
            request_id=ctx.request_id,
            query=query,
            summary=briefing,
            plan=plan,
            claims=claims,
            evidence_package_id=evidence_pkg_id,
            data_freshness="Near-real-time",
            limitations=limitations,
            audit_events=audit_events,
            status="completed",
        )
