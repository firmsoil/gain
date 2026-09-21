import json
from datetime import UTC, datetime
from pathlib import Path

import httpx

from gain.github.client import GitHubGraphQLClient

FIXTURE = Path(__file__).parent / "fixtures" / "graphql_page_1.json"


def test_graphql_client_parses_page_and_pagination() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/graphql"
        assert request.headers["authorization"] == "Bearer test-token"
        assert request.headers["x-github-api-version"] == "2022-11-28"
        return httpx.Response(200, json=payload)

    client = GitHubGraphQLClient(token="test-token", transport=httpx.MockTransport(handler))
    pages = list(
        client.iter_pull_request_pages(
            "acme",
            "example",
            since=datetime(2026, 1, 1, tzinfo=UTC),
            until=datetime(2026, 1, 31, tzinfo=UTC),
        )
    )
    assert len(pages) == 1
    assert pages[0].repository_name_with_owner == "acme/example"
    assert len(pages[0].nodes) == 2


def test_retry_on_transient_500() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(500, text="temporary")
        return httpx.Response(200, json=payload)

    client = GitHubGraphQLClient(
        token="test-token",
        max_retries=1,
        base_backoff_seconds=0.001,
        retry_max_backoff_seconds=0.001,
        transport=httpx.MockTransport(handler),
    )
    page = next(
        client.iter_pull_request_pages(
            "acme",
            "example",
            since=datetime(2026, 1, 1, tzinfo=UTC),
            until=datetime(2026, 1, 31, tzinfo=UTC),
        )
    )
    assert page.nodes
    assert calls == 2


def test_retry_on_rate_limit_429() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"retry-after": "0.001"}, text="rate limited")
        return httpx.Response(200, json=payload)

    client = GitHubGraphQLClient(
        token="test-token",
        max_retries=1,
        base_backoff_seconds=0.001,
        retry_max_backoff_seconds=0.001,
        jitter=False,
        transport=httpx.MockTransport(handler),
    )
    page = next(
        client.iter_pull_request_pages(
            "acme",
            "example",
            since=datetime(2026, 1, 1, tzinfo=UTC),
            until=datetime(2026, 1, 31, tzinfo=UTC),
        )
    )
    assert page.nodes
    assert calls == 2


def test_rate_limit_exhaustion_raises() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"retry-after": "0.001"}, text="rate limited")

    client = GitHubGraphQLClient(
        token="test-token",
        max_retries=1,
        base_backoff_seconds=0.001,
        retry_max_backoff_seconds=0.001,
        jitter=False,
        transport=httpx.MockTransport(handler),
    )
    import pytest

    from gain.errors import RateLimitError

    with pytest.raises(RateLimitError):
        list(
            client.iter_pull_request_pages(
                "acme",
                "example",
                since=datetime(2026, 1, 1, tzinfo=UTC),
                until=datetime(2026, 1, 31, tzinfo=UTC),
            )
        )


def test_network_timeout_raises_github_api_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("Connection timed out")

    client = GitHubGraphQLClient(
        token="test-token",
        max_retries=1,
        base_backoff_seconds=0.001,
        retry_max_backoff_seconds=0.001,
        jitter=False,
        transport=httpx.MockTransport(handler),
    )
    import pytest

    from gain.errors import GitHubApiError

    with pytest.raises(GitHubApiError):
        list(
            client.iter_pull_request_pages(
                "acme",
                "example",
                since=datetime(2026, 1, 1, tzinfo=UTC),
                until=datetime(2026, 1, 31, tzinfo=UTC),
            )
        )
