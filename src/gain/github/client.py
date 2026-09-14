from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx
import structlog

from gain.errors import GitHubApiError, IncompletePaginationError, RateLimitError
from gain.github.queries import PR_BACKFILL_QUERY

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class GraphQLPage:
    repository_id: str
    repository_name_with_owner: str
    nodes: list[dict[str, Any]]
    has_next_page: bool
    end_cursor: str | None


class GitHubGraphQLClient:
    def __init__(
        self,
        token: str,
        api_url: str = "https://api.github.com/graphql",
        page_size: int = 50,
        max_retries: int = 4,
        base_backoff_seconds: float = 1.0,
        retry_max_backoff_seconds: float = 30.0,
        timeout_seconds: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        self.api_url = api_url
        self.page_size = page_size
        self.max_retries = max_retries
        self.base_backoff_seconds = base_backoff_seconds
        self.retry_max_backoff_seconds = retry_max_backoff_seconds
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def _request(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        for attempt in range(self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout_seconds, transport=self.transport) as client:
                    response = client.post(
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
                    time.sleep(delay)
                    continue
                if 500 <= response.status_code < 600:
                    if attempt >= self.max_retries:
                        raise GitHubApiError(
                            f"GitHub server error {response.status_code}: {response.text[:500]}"
                        )
                    delay = self._retry_delay(attempt, None, None)
                    log.warning("github_server_error", attempt=attempt, delay_seconds=delay)
                    time.sleep(delay)
                    continue
                response.raise_for_status()
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
                time.sleep(delay)
        raise AssertionError("unreachable")

    def _retry_delay(self, attempt: int, retry_after: str | None, reset: str | None) -> float:
        if retry_after:
            try:
                return min(float(retry_after), self.retry_max_backoff_seconds)
            except ValueError:
                pass
        if reset:
            try:
                now = datetime.now(timezone.utc).timestamp()
                wait = max(0.0, float(reset) - now)
                if wait > 0:
                    return min(wait, self.retry_max_backoff_seconds)
            except ValueError:
                pass
        return min(self.base_backoff_seconds * (2**attempt), self.retry_max_backoff_seconds)

    def iter_pull_request_pages(
        self,
        owner: str,
        name: str,
        since: datetime,
        until: datetime,
        start_cursor: str | None = None,
    ) -> Iterator[GraphQLPage]:
        cursor = start_cursor
        while True:
            data = self._request(
                PR_BACKFILL_QUERY,
                {
                    "owner": owner,
                    "name": name,
                    "first": self.page_size,
                    "after": cursor,
                    "since": since.isoformat(),
                    "until": until.isoformat(),
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
                datetime.fromisoformat(str(node["createdAt"]).replace("Z", "+00:00"))
                for node in page.nodes
                if node.get("createdAt")
            ]
            if created_times and min(created_times) < since:
                return
            if not page.has_next_page:
                return
            if not page.end_cursor:
                raise IncompletePaginationError("GitHub indicated hasNextPage=true but no endCursor")
            if page.end_cursor == cursor:
                raise IncompletePaginationError("GitHub returned an unchanged pagination cursor")
            cursor = page.end_cursor
