"""Tool Router: Routes tool calls between GAIN MCP and GitHub MCP with failure isolation."""

from __future__ import annotations

from typing import Any

import structlog

from gain.agent.gain_mcp_client import GainMcpClient
from gain.agent.github_mcp_client import GitHubMcpClient, GitHubMcpUnavailableError

logger = structlog.get_logger(__name__)


class GainMcpUnavailableError(Exception):
    """Raised when GAIN MCP analytical service is offline or fails."""


class ToolRouter:
    """Manages dispatch and fault tolerance across dual MCP interfaces."""

    def __init__(
        self,
        gain_client: GainMcpClient | None = None,
        github_client: GitHubMcpClient | None = None,
    ) -> None:
        self.gain_client = gain_client or GainMcpClient()
        self.github_client = github_client or GitHubMcpClient()

    async def route_tool_call(
        self,
        target_system: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Dispatch a tool call to the designated target system with failure boundaries."""
        if target_system == "gain_mcp":
            return await self._execute_gain_tool(tool_name, arguments)
        if target_system == "github_mcp":
            return await self._execute_github_tool(tool_name, arguments)

        raise ValueError(f"Unknown target system '{target_system}'")

    async def _execute_gain_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool against GAIN MCP. Cannot fallback to ad-hoc GitHub calculation."""
        try:
            return await self.gain_client.call_tool(tool_name, arguments)
        except Exception as exc:
            logger.error("gain_mcp_call_failed", tool=tool_name, error=str(exc))
            raise GainMcpUnavailableError(
                f"Authoritative GAIN analytical service failed for tool '{tool_name}': {exc}"
            ) from exc

    async def _execute_github_tool(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute a tool against GitHub MCP. If unavailable, degrade gracefully."""
        try:
            return await self.github_client.call_tool(tool_name, arguments)
        except GitHubMcpUnavailableError as exc:
            logger.warning("github_mcp_call_degraded", tool=tool_name, reason=str(exc))
            return {
                "status": "unavailable",
                "system": "github_mcp",
                "tool": tool_name,
                "message": (
                    "Live GitHub operational context is unavailable. "
                    "Proceeding with analytical findings only."
                ),
                "degraded": True,
            }
        except Exception as exc:
            logger.error("github_mcp_call_unexpected_failure", tool=tool_name, error=str(exc))
            return {
                "status": "failed",
                "system": "github_mcp",
                "tool": tool_name,
                "error": str(exc),
                "degraded": True,
            }
