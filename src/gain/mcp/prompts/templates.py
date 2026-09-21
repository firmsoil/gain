"""Methodological MCP prompts for GAIN engineering intelligence."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer


def register_prompts(server: MCPServer) -> None:
    """Register domain-specific methodological prompts with the MCPServer."""

    @server.prompt(
        name="dora-executive-brief",
        description="Executive briefing prompt for DORA engineering metrics and delivery speed.",
    )
    def dora_executive_brief(population: str, time_window: str = "last-90-days") -> str:
        return (
            f"Please conduct an executive briefing on DORA metrics for population '{population}' "
            f"over '{time_window}'.\n\n"
            "Methodological Instructions:\n"
            "1. Call tool 'get_dora_metrics' with population and time_window.\n"
            "2. If telemetry is insufficient, report data gaps without fabricating values.\n"
            "3. Query 'query_engineering_metrics' for 'pr_cycle_time' and 'monthly_pr_flow_summary'"
            "\n   to establish baseline PR flow.\n"
            "4. Distinguish between 'Observed' metrics and 'Derived' or 'Modeled' projections.\n"
            "5. Deliver an executive summary covering throughput, lead times, and sufficiency."
        )

    @server.prompt(
        name="dora-investigation",
        description="Detailed investigation into delivery lead time and deployment anomalies.",
    )
    def dora_investigation(repository: str, anomaly_description: str) -> str:
        return (
            f"Investigate pipeline anomaly for repo '{repository}': '{anomaly_description}'.\n\n"
            "Methodological Instructions:\n"
            "1. Call 'start_investigation' with title and query parameters.\n"
            "2. Retrieve 'get_data_quality' for the repository dataset to ensure data validity.\n"
            "3. Query 'query_engineering_metrics' for 'pr_cycle_time' across trailing periods.\n"
            "4. Trace sample PRs using 'get_metric_lineage' for raw-to-canonical provenance.\n"
            "5. Synthesize findings citing evidence IDs and explicit limitations."
        )

    @server.prompt(
        name="ai-impact-investigation",
        description="Methodological framework for analyzing AI developer tooling impact.",
    )
    def ai_impact_investigation(cohort_a_repo: str, cohort_b_repo: str) -> str:
        return (
            f"Compare engineering flow between cohort '{cohort_a_repo}' and '{cohort_b_repo}'.\n\n"
            "Methodological Instructions:\n"
            "1. Call 'analyze_ai_impact' to determine data sufficiency and attribution taxonomy.\n"
            "2. Call 'compare_cohorts' to deterministically compare PR cycle time and throughput.\n"
            "3. Guardrail: Do NOT claim AI attribution without verified usage telemetry.\n"
            "4. Classify all claims strictly (Observed vs Derived vs Associated vs Unknown).\n"
            "5. Review data quality flags using 'get_data_quality' before drawing conclusions."
        )

    @server.prompt(
        name="ai-roi-analysis",
        description="Economic ROI scenario analysis for developer tooling investments.",
    )
    def ai_roi_analysis(time_period: str, population: str, investment_cost: float = 0.0) -> str:
        return (
            f"Evaluate an economic ROI scenario for population '{population}' over period "
            f"'{time_period}' with estimated investment cost ${investment_cost}.\n\n"
            "Methodological Instructions:\n"
            "1. Call 'calculate_ai_roi' with time_period and population.\n"
            "2. Clearly identify all economic and wage assumptions.\n"
            "3. Report outputs explicitly as 'Modeled' scenarios, NOT historical fact.\n"
            "4. Highlight sensitivity analysis, uncertainty intervals, and data prerequisites."
        )

    @server.prompt(
        name="metric-change-investigation",
        description="Investigate sudden shifts or trends in a specific GAIN engineering metric.",
    )
    def metric_change_investigation(metric_id: str, repository: str) -> str:
        return (
            f"Investigate changes in metric '{metric_id}' for repository '{repository}'.\n\n"
            "Methodological Instructions:\n"
            f"1. Call 'explain_metric' for '{metric_id}' to review authoritative definition.\n"
            "2. Query 'query_engineering_metrics' for trailing monthly stats.\n"
            "3. Examine distribution percentiles (p50 vs p90) to distinguish systemic shift.\n"
            "4. Inspect data quality flags with 'get_data_quality'.\n"
            "5. Document findings with concrete observation references."
        )

    @server.prompt(
        name="repository-engineering-investigation",
        description="Holistic engineering flow investigation for a specific GitHub repository.",
    )
    def repository_engineering_investigation(repository: str) -> str:
        return (
            f"Conduct a holistic engineering flow investigation for repository '{repository}'.\n\n"
            "Methodological Instructions:\n"
            "1. Call 'get_data_quality' to inspect dataset completeness, freshness, and validity.\n"
            "2. Query 'query_engineering_metrics' for cycle time and monthly flow.\n"
            "3. Call 'get_canonical_entity' on representative sample PRs to verify details.\n"
            "4. Summarize flow health, inventory (WIP), and merge throughput."
        )

    @server.prompt(
        name="evidence-review",
        description="Review and audit an existing GAIN evidence package for claim integrity.",
    )
    def evidence_review(evidence_id: str) -> str:
        return (
            f"Review and audit evidence package '{evidence_id}'.\n\n"
            "Methodological Instructions:\n"
            f"1. Call 'get_evidence' with '{evidence_id}'.\n"
            "2. Verify claim classification against the GAIN evidence hierarchy.\n"
            "3. Verify underlying metric definition using 'explain_metric'.\n"
            "4. Validate data freshness and statistical methodology.\n"
            "5. Issue an audit verdict: VALID, QUALIFIED, or DEFICIENT."
        )

    @server.prompt(
        name="engineering-health-briefing",
        description="Regular engineering health and flow briefing across repositories.",
    )
    def engineering_health_briefing(time_window: str = "last-30-days") -> str:
        return (
            f"Prepare an engineering health and flow briefing for '{time_window}'.\n\n"
            "Methodological Instructions:\n"
            "1. Query 'get_data_quality' to confirm dataset integrity.\n"
            "2. Query 'query_engineering_metrics' for cycle time distributions and monthly flow.\n"
            "3. Review throughput, cycle time trends, and open inventory.\n"
            "4. Conclude with observable workflow recommendations."
        )
