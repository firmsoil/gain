"""Tests for GAIN MCP transports (Streamable HTTP and stdio)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from starlette.routing import Route

from gain.mcp.server.app import create_mcp_server
from gain.mcp.transports.http import get_streamable_http_app, run_streamable_http_server
from gain.mcp.transports.stdio import run_stdio_server


def test_get_streamable_http_app() -> None:
    server = create_mcp_server()
    starlette_app = get_streamable_http_app(server, streamable_http_path="/mcp")
    assert starlette_app is not None
    # Inspect registered routes on Starlette app
    routes = [r.path for r in starlette_app.routes if isinstance(r, Route)]
    assert "/mcp" in routes


@pytest.mark.anyio
async def test_streamable_http_session_manager_lifecycle() -> None:
    server = create_mcp_server()
    _ = get_streamable_http_app(server)
    async with server.session_manager.run():
        # Verifies that session manager task group initializes and runs cleanly
        assert server.session_manager is not None


@pytest.mark.anyio
async def test_run_stdio_server_invokes_run_stdio_async() -> None:
    server = create_mcp_server()
    with patch.object(server, "run_stdio_async", new_callable=AsyncMock) as mock_run:
        await run_stdio_server(server)
        mock_run.assert_awaited_once()


@pytest.mark.anyio
async def test_run_streamable_http_server_invokes_async() -> None:
    server = create_mcp_server()
    with patch.object(server, "run_streamable_http_async", new_callable=AsyncMock) as mock_run:
        await run_streamable_http_server(
            server, host="127.0.0.1", port=9000, streamable_http_path="/gain-mcp"
        )
        mock_run.assert_awaited_once_with(
            host="127.0.0.1",
            port=9000,
            streamable_http_path="/gain-mcp",
            stateless_http=True,
        )
