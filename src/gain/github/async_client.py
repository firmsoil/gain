from __future__ import annotations

import asyncio
import random
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from types import TracebackType
from typing import Any, Self

import httpx
import structlog

from gain.errors import GitHubApiError, IncompletePaginationError, RateLimitError
from gain.github.auth import GitHubAuth, GitHubAuthProtocol, PATAuth
from gain.github.client import GraphQLPage
from gain.github.queries import PR_BACKFILL_QUERY
from gain.telemetry.metrics import GITHUB_RATE_LIMIT_REMAINING
from gain.util import parse_utc_datetime

log = structlog.get_logger(__name__)


class AsyncGitHubGraphQLClient:
    """Asynchronous client for GitHub's GraphQL API with persistent connection pooling."""

    def __init__(
        self,
        token: str | GitHubAuth | GitHubAuthProtocol | None = None,
        *,
        auth: str | GitHubAuth | GitHubAuthProtocol | None = None,
        api_url: str = "https://api.github.com/graphql",
        api_version: str = "2022-11-28",
        page_size: int = 50,
        max_retries: int = 4,
        base_backoff_seconds: float = 1.0,
        retry_max_backoff_seconds: float = 30.0,
        timeout_seconds: float = 30.0,
        timeout: httpx.Timeout | None = None,
        jitter: bool = True,
        transport: httpx.AsyncBaseTransport | None = None,
        limits: httpx.Limits | None = None,
    ) -> None:
        auth_input = auth if auth is not None else token
        if auth_input is None:
            raise ValueError("A GitHub token string or GitHubAuth instance is required.")
        if isinstance(auth_input, str):
            self._auth: GitHubAuthProtocol = PATAuth(token=auth_input)
        elif hasattr(auth_input, "get_token") or hasattr(auth_input, "token"):
            self._auth = auth_input
        else:
            raise TypeError(
                f"Expected str, GitHubAuth, or GitHubAuthProtocol, got {type(auth_input).__name__}"
            )

        self.api_url = api_url
        self.api_version = api_version
        self.page_size = page_size
        self.max_retries = max_retries
        self.base_backoff_seconds = base_backoff_seconds
        self.retry_max_backoff_seconds = retry_max_backoff_seconds
        self.timeout_seconds = timeout_seconds
        self.jitter = jitter
        self.transport = transport

        self.limits = (
            limits
            if limits is not None
            else httpx.Limits(max_connections=20, max_keepalive_connections=10)
        )
        self.timeout = (
            timeout if timeout is not None else httpx.Timeout(timeout_seconds, connect=10.0)
        )

        self._client: httpx.AsyncClient | None = None
        self._closed: bool = False

    def _get_token(self) -> str:
        if hasattr(self._auth, "get_token") and callable(self._auth.get_token):
            return str(self._auth.get_token())
        token_val = getattr(self._auth, "token", None)
        if token_val is not None:
            return str(token_val)
        raise TypeError(f"Invalid auth object: {type(self._auth).__name__}")

    @property
    def token(self) -> str:
        """Return the current active bearer token."""
        return self._get_token()

    @property
    def auth(self) -> GitHubAuthProtocol:
        """Return the underlying GitHubAuth credential provider."""
        return self._auth

    @property
    def is_closed(self) -> bool:
        """Return whether the client or underlying connection pool has been closed."""
        return self._closed or (self._client is not None and self._client.is_closed)

    @property
    def raw_client(self) -> httpx.AsyncClient:
        """Return the active httpx.AsyncClient connection pool, creating it if needed."""
        return self._get_client()

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": self.api_version,
        }

    def _get_client(self) -> httpx.AsyncClient:
        if self._closed:
            raise RuntimeError(
                "Client is closed: AsyncGitHubGraphQLClient has already been closed."
            )
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                transport=self.transport,
                limits=self.limits,
                timeout=self.timeout,
            )
        return self._client

    async def close(self) -> None:
        """Cleanly close the persistent HTTP connection pool."""
        self._closed = True
        if self._client is not None:
            try:
                if not self._client.is_closed:
                    await self._client.aclose()
            finally:
                self._client = None

    async def __aenter__(self) -> Self:
        client = self._get_client()
        await client.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        try:
            if self._client is not None:
                await self._client.__aexit__(exc_type, exc_val, exc_tb)
        finally:
            self._client = None
            self._closed = True

    async def _request(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        client = self._get_client()
        for attempt in range(self.max_retries + 1):
            try:
                response = await client.post(
                    self.api_url,
                    headers=self._headers,
                    json={"query": query, "variables": variables},
                )
                if response.status_code in {403, 429}:
                    retry_after = response.headers.get("retry-after")
                    reset = response.headers.get("x-ratelimit-reset")
                    if attempt >= self.max_retries:
                        raise RateLimitError(
                            f"GitHub rate limit after {self.max_retries + 1} attempts; "
                            f"status={response.status_code}"
                        )
                    delay = self._retry_delay(attempt, retry_after, reset)
                    log.warning("github_rate_limited", attempt=attempt, delay_seconds=delay)
                    await asyncio.sleep(delay)
                    continue
                if 500 <= response.status_code < 600:
                    if attempt >= self.max_retries:
                        raise GitHubApiError(
                            f"GitHub server error {response.status_code}: {response.text[:500]}"
                        )
                    delay = self._retry_delay(attempt, None, None)
                    log.warning("github_server_error", attempt=attempt, delay_seconds=delay)
                    await asyncio.sleep(delay)
                    continue
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    raise GitHubApiError(
                        f"GitHub HTTP error {response.status_code}: {response.text[:500]}"
                    ) from exc

                remaining_hdr = response.headers.get("x-ratelimit-remaining")
                reset_hdr = response.headers.get("x-ratelimit-reset")
                if remaining_hdr is not None:
                    try:
                        rem_val = float(remaining_hdr)
                        token_id = getattr(self._auth, "name", "default")
                        org_name = getattr(self._auth, "org", "global") or "global"
                        GITHUB_RATE_LIMIT_REMAINING.set(rem_val, token_id=token_id, org=org_name)
                        if reset_hdr is not None and hasattr(self._auth, "report_rate_limit"):
                            self._auth.report_rate_limit(
                                remaining=int(rem_val), reset_epoch=float(reset_hdr), used=1
                            )
                    except (ValueError, TypeError):
                        pass

                payload = response.json()
                graphql_errors = payload.get("errors") or []
                data = payload.get("data")
                if graphql_errors and data is None:
                    raise GitHubApiError(f"GraphQL errors: {graphql_errors}")
                if graphql_errors:
                    log.error("github_graphql_partial_errors", errors=graphql_errors)
                if not isinstance(data, dict):
                    raise GitHubApiError("GraphQL response did not contain an object in data")
                return data
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt >= self.max_retries:
                    raise GitHubApiError(f"GitHub network failure after retries: {exc}") from exc
                delay = self._retry_delay(attempt, None, None)
                log.warning("github_network_error", attempt=attempt, delay_seconds=delay)
                await asyncio.sleep(delay)
        raise AssertionError("unreachable")

    def _retry_delay(self, attempt: int, retry_after: str | None, reset: str | None) -> float:
        if retry_after:
            try:
                return min(float(retry_after), self.retry_max_backoff_seconds)
            except ValueError:
                pass
        if reset:
            try:
                now = datetime.now(UTC).timestamp()
                wait = max(0.0, float(reset) - now)
                if wait > 0:
                    return float(min(wait, self.retry_max_backoff_seconds))
            except ValueError:
                pass
        delay = min(self.base_backoff_seconds * (2**attempt), self.retry_max_backoff_seconds)
        if self.jitter:
            delay = delay * (0.5 + random.random() * 0.5)
        return float(delay)

    async def iter_pull_request_pages(
        self,
        owner: str,
        name: str,
        since: datetime,
        until: datetime,
        start_cursor: str | None = None,
    ) -> AsyncIterator[GraphQLPage]:
        cursor = start_cursor
        while True:
            data = await self._request(
                PR_BACKFILL_QUERY,
                {
                    "owner": owner,
                    "name": name,
                    "first": self.page_size,
                    "after": cursor,
                },
            )
            repository = data.get("repository")
            if repository is None:
                raise GitHubApiError(f"Repository not found or inaccessible: {owner}/{name}")
            connection = repository.get("pullRequests")
            if not isinstance(connection, dict):
                raise GitHubApiError("Missing pullRequests connection in GraphQL response")
            page_info = connection.get("pageInfo") or {}
            page = GraphQLPage(
                repository_id=str(repository["id"]),
                repository_name_with_owner=str(repository["nameWithOwner"]),
                nodes=list(connection.get("nodes") or []),
                has_next_page=bool(page_info.get("hasNextPage")),
                end_cursor=page_info.get("endCursor"),
            )
            yield page

            # The connection is ordered newest-first. Once the oldest record on a page
            # predates the requested lower bound, no later page can contain an in-window PR.
            created_times = [
                parse_utc_datetime(str(node["createdAt"]))
                for node in page.nodes
                if node.get("createdAt")
            ]
            if created_times and min(created_times) < since:
                return
            if not page.has_next_page:
                return
            if not page.end_cursor:
                raise IncompletePaginationError(
                    "GitHub indicated hasNextPage=true but no endCursor"
                )
            if page.end_cursor == cursor:
                raise IncompletePaginationError("GitHub returned an unchanged pagination cursor")
            cursor = page.end_cursor


__all__ = ["AsyncGitHubGraphQLClient", "GitHubAuth", "GitHubAuthProtocol", "GraphQLPage"]
