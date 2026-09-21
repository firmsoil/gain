"""Standard I/O transport runner for GAIN MCP."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer


async def run_stdio_server(server: MCPServer) -> None:
    """Run the MCPServer over stdio transport asynchronously."""
    await server.run_stdio_async()


def run_stdio(server: MCPServer) -> None:
    """Synchronous entry point to run MCPServer over stdio."""
    asyncio.run(run_stdio_server(server))
