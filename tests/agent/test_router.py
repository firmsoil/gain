"""Unit tests for ToolRouter and failure isolation."""

import pytest

from gain.agent.gain_mcp_client import GainMcpClient
from gain.agent.github_mcp_client import GitHubMcpClient
from gain.agent.router import GainMcpUnavailableError, ToolRouter


@pytest.mark.anyio
async def test_tool_router_executes_gain_tool() -> None:
    router = ToolRouter()
    # explain_metric does not require populated repo data, just metric catalog
    res = await router.route_tool_call(
        target_system="gain_mcp",
        tool_name="explain_metric",
        arguments={"metric_id": "GAIN-PR-001"},
    )
    assert res["metric_id"] == "GAIN-PR-001"
    assert res["name"] == "pr_cycle_time"


@pytest.mark.anyio
async def test_tool_router_handles_github_mcp_offline_gracefully() -> None:
    # Unconfigured GitHub MCP client (no endpoint, mock_mode=False)
    unconfigured_gh = GitHubMcpClient(endpoint_url=None, mock_mode=False)
    router = ToolRouter(github_client=unconfigured_gh)

    res = await router.route_tool_call(
        target_system="github_mcp",
        tool_name="get_pull_request_details",
        arguments={"repo": "firmsoil/gain"},
    )

    assert res["status"] == "unavailable"
    assert res["degraded"] is True
    assert "Live GitHub operational context is unavailable" in res["message"]


@pytest.mark.anyio
async def test_tool_router_handles_mock_github_tool() -> None:
    mock_gh = GitHubMcpClient(mock_mode=True)
    router = ToolRouter(github_client=mock_gh)

    res = await router.route_tool_call(
        target_system="github_mcp",
        tool_name="get_pull_request_details",
        arguments={"repo": "firmsoil/gain"},
    )

    assert res["repository"] == "firmsoil/gain"
    assert len(res["pull_requests"]) >= 1


@pytest.mark.anyio
async def test_tool_router_gain_failure_raises_explicit_error() -> None:
    class FailingGainClient(GainMcpClient):
        async def call_tool(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
            raise RuntimeError("Database connection timed out")

    router = ToolRouter(gain_client=FailingGainClient())

    with pytest.raises(
        GainMcpUnavailableError, match="Authoritative GAIN analytical service failed"
    ):
        await router.route_tool_call(
            target_system="gain_mcp",
            tool_name="query_engineering_metrics",
            arguments={"metric_id": "GAIN-PR-001", "repo": "firmsoil/gain"},
        )
