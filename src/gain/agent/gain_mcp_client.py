"""GAIN MCP Client: Governed client for invoking GAIN MCP domain tools."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

import structlog

from gain.mcp.errors import MCPError
from gain.mcp.tools import (
    analyze_ai_impact,
    calculate_ai_roi,
    compare_cohorts,
    explain_metric,
    get_canonical_entity,
    get_data_quality,
    get_dora_metrics,
    get_evidence,
    get_investigation,
    get_metric_lineage,
    query_engineering_metrics,
    start_investigation,
)

logger = structlog.get_logger(__name__)

TOOL_DISPATCH_MAP: dict[str, Callable[..., Any]] = {
    "get_dora_metrics": get_dora_metrics,
    "query_engineering_metrics": query_engineering_metrics,
    "compare_cohorts": compare_cohorts,
    "analyze_ai_impact": analyze_ai_impact,
    "calculate_ai_roi": calculate_ai_roi,
    "explain_metric": explain_metric,
    "get_metric_lineage": get_metric_lineage,
    "get_evidence": get_evidence,
    "start_investigation": start_investigation,
    "get_investigation": get_investigation,
    "get_data_quality": get_data_quality,
    "get_canonical_entity": get_canonical_entity,
}


class GainMcpClient:
    """Client for executing governed domain tools against the GAIN MCP interface."""

    def __init__(self) -> None:
        self.available_tools = set(TOOL_DISPATCH_MAP.keys())

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Invoke a GAIN MCP tool and return a JSON-serializable dictionary output."""
        if name not in TOOL_DISPATCH_MAP:
            raise MCPError(f"Tool '{name}' is not registered with GAIN MCP Server")

        fn = TOOL_DISPATCH_MAP[name]
        logger.info("gain_mcp_tool_invoking", tool=name, args=list(arguments.keys()))

        try:
            import inspect

            if inspect.iscoroutinefunction(fn):
                res = await fn(**arguments)
            else:
                res = fn(**arguments)

            if hasattr(res, "model_dump"):
                return cast(dict[str, Any], res.model_dump(mode="json"))
            if isinstance(res, dict):
                return cast(dict[str, Any], res)
            return {"result": str(res)}
        except Exception as exc:
            logger.error("gain_mcp_tool_failed", tool=name, error=str(exc))
            raise
