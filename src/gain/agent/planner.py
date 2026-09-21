"""Investigation Planner: Translates user queries into structured, executable plans."""

from __future__ import annotations

import re
from uuid import uuid4

import structlog

from gain.agent.models import InvestigationContext, InvestigationPlan, PlanStep

logger = structlog.get_logger(__name__)


class InvestigationPlanner:
    """Creates deterministic and hypothesis-driven investigation plans."""

    def create_plan(
        self,
        query: str,
        context: InvestigationContext,
        default_repo: str = "firmsoil/gain",
    ) -> InvestigationPlan:
        """Analyze query intent and generate a structured InvestigationPlan."""
        q_lower = query.lower()
        repo = self._extract_repository(query) or default_repo
        plan_id = f"plan-{uuid4().hex[:8]}"

        steps: list[PlanStep] = []

        if re.search(r"\b(roi|economic|financial|savings)\b", q_lower):
            methodology = "AI Developer Tooling Economic ROI Scenario"
            steps = self._build_ai_roi_plan(repo)
        elif re.search(r"\b(ai|copilot|attribution|impact)\b", q_lower):
            methodology = "AI Delivery Impact & Attribution Investigation"
            steps = self._build_ai_impact_plan(repo)
        elif re.search(r"\b(dora|deployment|lead time|fail rate)\b", q_lower):
            methodology = "DORA Delivery Flow & Operational Assessment"
            steps = self._build_dora_plan(repo)
        elif re.search(r"\b(jira|linear|issue|issues|story|ticket)\b", q_lower):
            methodology = "Work Item & Issue Delivery Flow Investigation"
            steps = self._build_issue_flow_plan(repo)
        elif re.search(r"\b(compare|cohort|vs|difference)\b", q_lower):
            methodology = "Comparative Cohort Engineering Analysis"
            steps = self._build_cohort_comparison_plan(repo)
        elif re.search(r"\b(lineage|provenance|audit|trace)\b", q_lower):
            methodology = "Metric Lineage & Provenance Verification"
            steps = self._build_lineage_plan(repo)
        else:
            methodology = "Engineering Flow & Cycle-Time Root-Cause Investigation"
            steps = self._build_default_cycle_time_plan(repo)

        plan = InvestigationPlan(
            plan_id=plan_id,
            investigation_id=context.investigation_id,
            intent=query,
            methodology=methodology,
            repository=repo,
            steps=steps,
        )

        logger.info(
            "investigation_plan_created",
            plan_id=plan.plan_id,
            investigation_id=plan.investigation_id,
            methodology=plan.methodology,
            step_count=len(plan.steps),
        )
        return plan

    def _extract_repository(self, text: str) -> str | None:
        """Detect repository name with owner pattern (e.g. 'org/repo')."""
        match = re.search(r"\b([a-zA-Z0-9_\-\.]+/[a-zA-Z0-9_\-\.]+)\b", text)
        return match.group(1) if match else None

    def _build_default_cycle_time_plan(self, repo: str) -> list[PlanStep]:
        return [
            PlanStep(
                step_id="step-1",
                description=f"Query PR cycle-time metric distribution for {repo}",
                tool_name="query_engineering_metrics",
                target_system="gain_mcp",
                arguments={"metric_name": "GAIN-PR-001", "repository": repo},
                dependencies=[],
            ),
            PlanStep(
                step_id="step-2",
                description="Retrieve authoritative metric definition from Metric Catalog",
                tool_name="explain_metric",
                target_system="gain_mcp",
                arguments={"metric_id": "GAIN-PR-001"},
                dependencies=[],
            ),
            PlanStep(
                step_id="step-3",
                description=f"Evaluate dataset health and freshness for {repo}",
                tool_name="get_data_quality",
                target_system="gain_mcp",
                arguments={"dataset_id": "pull_requests"},
                dependencies=[],
            ),
            PlanStep(
                step_id="step-4",
                description=f"Retrieve live contextual PR details from GitHub for {repo}",
                tool_name="get_pull_request_details",
                target_system="github_mcp",
                arguments={"repo": repo, "limit": 3},
                dependencies=["step-1"],
            ),
        ]

    def _build_ai_impact_plan(self, repo: str) -> list[PlanStep]:
        return [
            PlanStep(
                step_id="step-1",
                description=f"Check AI attribution telemetry prerequisites and impact for {repo}",
                tool_name="analyze_ai_impact",
                target_system="gain_mcp",
                arguments={"cohort_definition": {"repository": repo}},
                dependencies=[],
            ),
            PlanStep(
                step_id="step-2",
                description=f"Query underlying PR flow baseline for {repo}",
                tool_name="query_engineering_metrics",
                target_system="gain_mcp",
                arguments={"metric_name": "GAIN-PR-001", "repository": repo},
                dependencies=[],
            ),
            PlanStep(
                step_id="step-3",
                description=f"Evaluate data quality and telemetry freshness for {repo}",
                tool_name="get_data_quality",
                target_system="gain_mcp",
                arguments={"dataset_id": "pull_requests"},
                dependencies=[],
            ),
        ]

    def _build_dora_plan(self, repo: str) -> list[PlanStep]:
        return [
            PlanStep(
                step_id="step-1",
                description=f"Query canonical DORA metrics for {repo}",
                tool_name="get_dora_metrics",
                target_system="gain_mcp",
                arguments={"population": repo, "time_window": "last_30_days", "repository": repo},
                dependencies=[],
            ),
            PlanStep(
                step_id="step-2",
                description=f"Query engineering flow metrics for PR delivery in {repo}",
                tool_name="query_engineering_metrics",
                target_system="gain_mcp",
                arguments={"metric_name": "GAIN-PR-001", "repository": repo},
                dependencies=[],
            ),
            PlanStep(
                step_id="step-3",
                description=f"Evaluate canonical dataset quality for {repo}",
                tool_name="get_data_quality",
                target_system="gain_mcp",
                arguments={"dataset_id": "pull_requests"},
                dependencies=[],
            ),
        ]

    def _build_cohort_comparison_plan(self, repo: str) -> list[PlanStep]:
        return [
            PlanStep(
                step_id="step-1",
                description=f"Compare engineering flow cohorts in {repo}",
                tool_name="compare_cohorts",
                target_system="gain_mcp",
                arguments={
                    "cohort_a_repo": repo,
                    "cohort_b_repo": repo,
                    "metric_name": "pr_cycle_time",
                },
                dependencies=[],
            ),
            PlanStep(
                step_id="step-2",
                description=f"Evaluate dataset health for {repo}",
                tool_name="get_data_quality",
                target_system="gain_mcp",
                arguments={"dataset_id": "pull_requests"},
                dependencies=[],
            ),
        ]

    def _build_lineage_plan(self, repo: str) -> list[PlanStep]:
        return [
            PlanStep(
                step_id="step-1",
                description=f"Trace provenance from raw capture to metric observation in {repo}",
                tool_name="get_metric_lineage",
                target_system="gain_mcp",
                arguments={"target_id": "obs-001"},
                dependencies=[],
            ),
            PlanStep(
                step_id="step-2",
                description="Retrieve authoritative metric definition",
                tool_name="explain_metric",
                target_system="gain_mcp",
                arguments={"metric_id": "GAIN-PR-001"},
                dependencies=[],
            ),
        ]

    def _build_ai_roi_plan(self, repo: str) -> list[PlanStep]:
        return [
            PlanStep(
                step_id="step-1",
                description=f"Check AI attribution telemetry prerequisites and impact for {repo}",
                tool_name="analyze_ai_impact",
                target_system="gain_mcp",
                arguments={"cohort_definition": {"repository": repo}},
                dependencies=[],
            ),
            PlanStep(
                step_id="step-2",
                description=f"Calculate economic ROI scenarios for {repo}",
                tool_name="calculate_ai_roi",
                target_system="gain_mcp",
                arguments={"time_period": "annual", "population": repo},
                dependencies=[],
            ),
            PlanStep(
                step_id="step-3",
                description=f"Evaluate dataset health for {repo}",
                tool_name="get_data_quality",
                target_system="gain_mcp",
                arguments={"dataset_id": "pull_requests"},
                dependencies=[],
            ),
        ]

    def _build_issue_flow_plan(self, repo: str) -> list[PlanStep]:
        return [
            PlanStep(
                step_id="step-1",
                description=f"Query canonical work item cycle-time and throughput for {repo}",
                tool_name="query_engineering_metrics",
                target_system="gain_mcp",
                arguments={"metric_name": "GAIN-ISSUE-001", "repository": repo},
                dependencies=[],
            ),
            PlanStep(
                step_id="step-2",
                description=f"Query PR cycle-time metrics for delivery correlation in {repo}",
                tool_name="query_engineering_metrics",
                target_system="gain_mcp",
                arguments={"metric_name": "GAIN-PR-001", "repository": repo},
                dependencies=[],
            ),
            PlanStep(
                step_id="step-3",
                description=f"Evaluate canonical dataset quality for {repo}",
                tool_name="get_data_quality",
                target_system="gain_mcp",
                arguments={"dataset_id": "pull_requests"},
                dependencies=[],
            ),
        ]
