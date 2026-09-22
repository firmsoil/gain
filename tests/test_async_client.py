from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from gain.errors import GitHubApiError, RateLimitError
from gain.github.async_client import AsyncGitHubGraphQLClient


def _make_page_response(
    nodes: list[dict[str, Any]],
    has_next: bool = False,
    end_cursor: str | None = None,
) -> dict[str, Any]:
    return {
        "data": {
            "repository": {
                "id": "R_TEST_001",
                "nameWithOwner": "acme/test-repo",
                "pullRequests": {
                    "nodes": nodes,
                    "pageInfo": {
                        "hasNextPage": has_next,
                        "endCursor": end_cursor,
                    },
                },
            }
        }
    }


@pytest.mark.anyio
async def test_async_iter_pull_request_pages_multi_page() -> None:
    page1_nodes = [
        {
            "id": "PR_1",
            "number": 1,
            "author": {"__typename": "User", "login": "alice"},
            "createdAt": "2026-06-15T12:00:00Z",
            "closedAt": None,
            "mergedAt": None,
            "state": "OPEN",
            "isDraft": False,
            "additions": 10,
            "deletions": 5,
            "changedFiles": 2,
            "reviewDecision": "APPROVED",
        }
    ]
    page2_nodes = [
        {
            "id": "PR_2",
            "number": 2,
            "author": {"__typename": "User", "login": "bob"},
            "createdAt": "2026-06-14T10:00:00Z",
            "closedAt": "2026-06-14T11:00:00Z",
            "mergedAt": "2026-06-14T11:00:00Z",
            "state": "MERGED",
            "isDraft": False,
            "additions": 20,
            "deletions": 0,
            "changedFiles": 1,
            "reviewDecision": None,
        }
    ]

    call_count = 0

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        body = json.loads(request.content.decode("utf-8"))
        after = body.get("variables", {}).get("after")
        if after is None:
            return httpx.Response(
                200, json=_make_page_response(page1_nodes, has_next=True, end_cursor="cursor_1")
            )
        return httpx.Response(
            200, json=_make_page_response(page2_nodes, has_next=False, end_cursor="cursor_2")
        )

    transport = httpx.MockTransport(mock_handler)
    client = AsyncGitHubGraphQLClient(
        token="ghp_test_token_123",
        transport=transport,
        jitter=False,
    )

    since = datetime(2026, 6, 1, tzinfo=UTC)
    until = datetime(2026, 6, 30, tzinfo=UTC)

    pages = []
    async for page in client.iter_pull_request_pages("acme", "test-repo", since=since, until=until):
        pages.append(page)

    assert len(pages) == 2
    assert pages[0].repository_id == "R_TEST_001"
    assert pages[0].repository_name_with_owner == "acme/test-repo"
    assert len(pages[0].nodes) == 1
    assert pages[0].nodes[0]["id"] == "PR_1"
    assert len(pages[1].nodes) == 1
    assert pages[1].nodes[0]["id"] == "PR_2"
    assert call_count == 2
    await client.close()


@pytest.mark.anyio
async def test_async_retry_on_rate_limit_and_recover() -> None:
    attempts = 0

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(
                429,
                headers={"retry-after": "0", "x-ratelimit-remaining": "0"},
                json={"message": "rate limited"},
            )
        return httpx.Response(200, json=_make_page_response([]))

    transport = httpx.MockTransport(mock_handler)
    client = AsyncGitHubGraphQLClient(
        token="ghp_test_token_123",
        transport=transport,
        base_backoff_seconds=0.01,
        jitter=False,
    )

    async with client:
        pages = [
            page
            async for page in client.iter_pull_request_pages(
                "acme",
                "test-repo",
                since=datetime(2026, 1, 1, tzinfo=UTC),
                until=datetime(2026, 1, 2, tzinfo=UTC),
            )
        ]

    assert len(pages) == 1
    assert attempts == 2


@pytest.mark.anyio
async def test_async_retry_exhaustion_raises_rate_limit_error() -> None:
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            headers={"retry-after": "0"},
            json={"message": "rate limited permanently"},
        )

    transport = httpx.MockTransport(mock_handler)
    client = AsyncGitHubGraphQLClient(
        token="ghp_test_token_123",
        transport=transport,
        max_retries=2,
        base_backoff_seconds=0.01,
        jitter=False,
    )

    with pytest.raises(RateLimitError):
        async with client:
            async for _ in client.iter_pull_request_pages(
                "acme",
                "test-repo",
                since=datetime(2026, 1, 1, tzinfo=UTC),
                until=datetime(2026, 1, 2, tzinfo=UTC),
            ):
                pass


@pytest.mark.anyio
async def test_async_server_error_exhaustion_raises_github_api_error() -> None:
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="Bad Gateway")

    transport = httpx.MockTransport(mock_handler)
    client = AsyncGitHubGraphQLClient(
        token="ghp_test_token_123",
        transport=transport,
        max_retries=2,
        base_backoff_seconds=0.01,
        jitter=False,
    )

    with pytest.raises(GitHubApiError):
        async with client:
            async for _ in client.iter_pull_request_pages(
                "acme",
                "test-repo",
                since=datetime(2026, 1, 1, tzinfo=UTC),
                until=datetime(2026, 1, 2, tzinfo=UTC),
            ):
                pass


@pytest.mark.anyio
async def test_async_client_context_manager_lifecycle() -> None:
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_make_page_response([]))

    transport = httpx.MockTransport(mock_handler)
    client = AsyncGitHubGraphQLClient(
        token="ghp_test_token_123",
        transport=transport,
    )

    assert not client.is_closed
    async with client as active_client:
        assert active_client is client
        assert not client.is_closed
        # perform a request
        pages = [
            page
            async for page in client.iter_pull_request_pages(
                "acme",
                "test-repo",
                since=datetime(2026, 1, 1, tzinfo=UTC),
                until=datetime(2026, 1, 2, tzinfo=UTC),
            )
        ]
        assert len(pages) == 1

    assert client.is_closed
    # Further calls raise RuntimeError because client was closed
    with pytest.raises(RuntimeError, match="has already been closed"):
        async for _ in client.iter_pull_request_pages(
            "acme",
            "test-repo",
            since=datetime(2026, 1, 1, tzinfo=UTC),
            until=datetime(2026, 1, 2, tzinfo=UTC),
        ):
            pass


@pytest.mark.anyio
async def test_async_iter_pull_request_pages_stops_at_since_boundary() -> None:
    # Newest-first: first item is within window, second is older than since
    nodes = [
        {
            "id": "PR_NEW",
            "number": 10,
            "createdAt": "2026-06-15T12:00:00Z",
            "closedAt": None,
            "mergedAt": None,
            "state": "OPEN",
            "isDraft": False,
        },
        {
            "id": "PR_OLD",
            "number": 9,
            "createdAt": "2026-05-01T12:00:00Z",  # older than since (2026-06-01)
            "closedAt": None,
            "mergedAt": None,
            "state": "OPEN",
            "isDraft": False,
        },
    ]

    call_count = 0

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            200, json=_make_page_response(nodes, has_next=True, end_cursor="cursor_next")
        )

    transport = httpx.MockTransport(mock_handler)
    client = AsyncGitHubGraphQLClient(
        token="ghp_test_token_123",
        transport=transport,
    )

    since = datetime(2026, 6, 1, tzinfo=UTC)
    until = datetime(2026, 6, 30, tzinfo=UTC)

    pages = []
    async with client:
        async for page in client.iter_pull_request_pages(
            "acme", "test-repo", since=since, until=until
        ):
            pages.append(page)

    # Should have fetched page 1, discovered oldest node is < since,
    # and stopped iterating (call_count == 1)
    assert len(pages) == 1
    assert call_count == 1
