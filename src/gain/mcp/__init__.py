"""GAIN Model Context Protocol (MCP) Server package."""

from __future__ import annotations

from typing import Any


def __getattr__(name: str) -> Any:
    if name == "create_mcp_server":
        from gain.mcp.server.app import create_mcp_server

        return create_mcp_server
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["create_mcp_server"]
