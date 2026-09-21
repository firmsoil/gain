"""GAIN MCP tool catalog and registration."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from gain.mcp.tools.ai import analyze_ai_impact, calculate_ai_roi
from gain.mcp.tools.entity import get_canonical_entity
from gain.mcp.tools.evidence import get_evidence
from gain.mcp.tools.investigation import get_investigation, start_investigation
from gain.mcp.tools.lineage import get_metric_lineage
from gain.mcp.tools.metrics import (
    compare_cohorts,
    explain_metric,
    get_dora_metrics,
    query_engineering_metrics,
)
from gain.mcp.tools.quality import get_data_quality

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

ALL_TOOLS: list[tuple[Callable[..., Any], str, str]] = [
    (
        get_dora_metrics,
        "get_dora_metrics",
        "Retrieve current GAIN DORA metrics for population/window.",
    ),
    (
        query_engineering_metrics,
        "query_engineering_metrics",
        "Execute approved GAIN engineering metrics (e.g. pr_cycle_time).",
    ),
    (
        compare_cohorts,
        "compare_cohorts",
        "Compare two populations using approved deterministic metrics.",
    ),
    (
        analyze_ai_impact,
        "analyze_ai_impact",
        "Expose GAIN AI impact analytical service with strict attribution taxonomy.",
    ),
    (
        calculate_ai_roi,
        "calculate_ai_roi",
        "Expose GAIN economic-model scenario service for AI developer tooling.",
    ),
    (
        explain_metric,
        "explain_metric",
        "Explain definition and calculation methodology of a named metric from catalog.",
    ),
    (
        get_metric_lineage,
        "get_metric_lineage",
        "Return end-to-end source-to-result lineage for an entity or observation.",
    ),
    (
        get_evidence,
        "get_evidence",
        "Retrieve a previously generated structured evidence package by ID.",
    ),
    (
        start_investigation,
        "start_investigation",
        "Create durable GAIN investigation state for an authorized investigation.",
    ),
    (
        get_investigation,
        "get_investigation",
        "Retrieve persisted investigation status/result within authorized tenant.",
    ),
    (
        get_data_quality,
        "get_data_quality",
        "Return data quality metrics: freshness, completeness, validity, and gaps.",
    ),
    (
        get_canonical_entity,
        "get_canonical_entity",
        "Retrieve a canonical GAIN entity (PullRequest) by authorized identifier.",
    ),
]


def register_tools(server: MCPServer) -> None:
    """Register all 12 domain tools with the MCPServer instance."""
    for fn, name, desc in ALL_TOOLS:
        server.add_tool(fn, name=name, description=desc)


__all__ = [
    "ALL_TOOLS",
    "analyze_ai_impact",
    "calculate_ai_roi",
    "compare_cohorts",
    "explain_metric",
    "get_canonical_entity",
    "get_data_quality",
    "get_dora_metrics",
    "get_evidence",
    "get_investigation",
    "get_metric_lineage",
    "query_engineering_metrics",
    "register_tools",
    "start_investigation",
]
