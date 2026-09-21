"""GAIN MCP server package."""

from __future__ import annotations

from gain.mcp.server.app import create_mcp_server
from gain.mcp.server.instructions import SERVER_INSTRUCTIONS

__all__ = ["SERVER_INSTRUCTIONS", "create_mcp_server"]
