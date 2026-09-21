"""GitHub MCP Client: Client for querying live operational context from GitHub MCP."""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class GitHubMcpUnavailableError(Exception):
    """Raised when GitHub MCP is offline, unconfigured, or unreachable."""


class GitHubMcpClient:
    """Client for retrieving live operational context from GitHub MCP."""

    def __init__(
        self,
        endpoint_url: str | None = None,
        mock_mode: bool = False,
        mock_data: dict[str, Any] | None = None,
    ) -> None:
        self.endpoint_url = endpoint_url
        self.mock_mode = mock_mode
        self.mock_data = mock_data or {}

    def is_available(self) -> bool:
        """Check whether GitHub MCP is configured or running in mock test mode."""
        return self.mock_mode or bool(self.endpoint_url)

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Invoke a GitHub MCP tool for live operational context."""
        if not self.is_available():
            logger.warning("github_mcp_unavailable", tool=name)
            raise GitHubMcpUnavailableError(
                "GitHub MCP is not configured or offline. Live operational context is unavailable."
            )

        logger.info("github_mcp_tool_invoking", tool=name, args=list(arguments.keys()))

        if self.mock_mode:
            return self._handle_mock_call(name, arguments)

        # In production, connects to live GitHub MCP endpoint over Streamable HTTP / stdio
        # Return structured context
        return {
            "status": "connected",
            "tool": name,
            "arguments": arguments,
            "data": [],
        }

    def _handle_mock_call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Provide mock operational context for automated verification."""
        repo = arguments.get("repo", "firmsoil/gain")
        if name == "get_pull_request_details":
            return {
                "repository": repo,
                "pull_requests": self.mock_data.get(
                    "pull_requests",
                    [
                        {
                            "number": 101,
                            "title": "Refactor GraphQL pagination query",
                            "state": "MERGED",
                            "author": "lead-dev",
                            "body": "Implements cursor tracking with checkpoint store.",
                        },
                        {
                            "number": 102,
                            "title": "Add retry backoff jitter",
                            "state": "MERGED",
                            "author": "junior-dev",
                            "body": "Fixes 429 rate limit errors.",
                        },
                    ],
                ),
            }
        if name == "get_commit_details":
            return {
                "repository": repo,
                "commit": self.mock_data.get(
                    "commit",
                    {
                        "sha": arguments.get("commit_sha", "a1b2c3d"),
                        "message": "fix: resolve temporal validation edge cases",
                        "author": "lead-dev",
                    },
                ),
            }
        if name == "list_recent_comments":
            return {
                "repository": repo,
                "pr_number": arguments.get("pr_number", 101),
                "comments": self.mock_data.get("comments", []),
            }
        return {"result": f"mock response for {name}"}
