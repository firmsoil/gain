"""Streamable HTTP transport runner and Starlette ASGI application provider for GAIN MCP."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from gain.config import Settings
from gain.github.token_pool import GitHubTokenPool
from gain.mcp.health import add_health_endpoints

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer
    from starlette.applications import Starlette


def get_streamable_http_app(
    server: MCPServer,
    streamable_http_path: str = "/mcp",
    stateless_http: bool = True,
    *,
    settings: Settings | None = None,
    token_pool: GitHubTokenPool | None = None,
    include_health_endpoints: bool = True,
) -> Starlette:
    """Return the Starlette ASGI application configured for Streamable HTTP."""
    app = server.streamable_http_app(
        streamable_http_path=streamable_http_path,
        stateless_http=stateless_http,
    )
    if include_health_endpoints:
        add_health_endpoints(app, settings=settings, token_pool=token_pool)
    return app


async def run_streamable_http_server(
    server: MCPServer,
    host: str = "127.0.0.1",
    port: int = 8000,
    streamable_http_path: str = "/mcp",
    stateless_http: bool = True,
) -> None:
    """Run the MCPServer over Streamable HTTP transport using Uvicorn."""
    await server.run_streamable_http_async(
        host=host,
        port=port,
        streamable_http_path=streamable_http_path,
        stateless_http=stateless_http,
    )


def run_streamable_http(
    server: MCPServer,
    host: str = "127.0.0.1",
    port: int = 8000,
    streamable_http_path: str = "/mcp",
    stateless_http: bool = True,
) -> None:
    """Synchronous entry point to run MCPServer over Streamable HTTP."""
    asyncio.run(
        run_streamable_http_server(
            server=server,
            host=host,
            port=port,
            streamable_http_path=streamable_http_path,
            stateless_http=stateless_http,
        )
    )
