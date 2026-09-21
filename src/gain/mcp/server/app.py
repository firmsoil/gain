"""Factory for creating and configuring the GAIN MCPServer instance."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from gain.mcp.prompts import register_prompts
from gain.mcp.resources import register_resources
from gain.mcp.server.instructions import SERVER_INSTRUCTIONS
from gain.mcp.tools import register_tools


def create_mcp_server(
    name: str = "gain-mcp-server",
    version: str = "0.1.0",
) -> MCPServer:
    """Create and configure a production-grade GAIN MCPServer instance."""
    server = MCPServer(
        name=name,
        version=version,
        title="GAIN — GitHub AI Intelligence Network MCP Server",
        description=(
            "Domain-oriented Model Context Protocol server exposing deterministic "
            "engineering intelligence."
        ),
        instructions=SERVER_INSTRUCTIONS,
    )

    # Register all domain interfaces
    register_tools(server)
    register_resources(server)
    register_prompts(server)

    return server


# Default server instance for MCP Inspector and direct runners
server = create_mcp_server()
