from __future__ import annotations

import time
from pathlib import Path

import httpx
import pytest
from starlette.routing import Route

from gain.config import Settings
from gain.github.auth import PATAuth
from gain.github.token_pool import GitHubTokenPool
from gain.mcp.health import (
    check_liveness,
    check_readiness,
)
from gain.mcp.server.app import create_mcp_server
from gain.mcp.transports.http import get_streamable_http_app


def test_check_liveness() -> None:
    result = check_liveness()
    assert result == {"status": "ok"}


def test_check_readiness_healthy(tmp_path: Path) -> None:
    settings = Settings(
        raw_dir=tmp_path / "raw",
        canonical_dir=tmp_path / "canonical",
        output_dir=tmp_path / "output",
        github_token="ghp_test_readiness",
    )
    token1 = PATAuth(token="ghp_1", name="token-1")
    token_pool = GitHubTokenPool([token1])

    report = check_readiness(settings=settings, token_pool=token_pool)
    assert report.status == "ok"
    assert report.version == "0.1.0"
    assert report.checks["raw_storage"].status == "ok"
    assert report.checks["canonical_storage"].status == "ok"
    assert report.checks["github_tokens"].status == "ok"


def test_check_readiness_token_degraded_and_exhausted(tmp_path: Path) -> None:
    settings = Settings(
        raw_dir=tmp_path / "raw",
        canonical_dir=tmp_path / "canonical",
        output_dir=tmp_path / "output",
    )
    token1 = PATAuth(token="ghp_1", name="token-1")
    token2 = PATAuth(token="ghp_2", name="token-2")
    token_pool = GitHubTokenPool([token1, token2])

    # Mark token1 exhausted
    token1.report_rate_limit(remaining=0, reset_epoch=time.time() + 3600)
    report = check_readiness(settings=settings, token_pool=token_pool)
    assert report.status == "degraded"
    assert report.checks["github_tokens"].status == "degraded"

    # Mark token2 exhausted too
    token2.report_rate_limit(remaining=0, reset_epoch=time.time() + 3600)
    report_exhausted = check_readiness(settings=settings, token_pool=token_pool)
    assert report_exhausted.status == "unhealthy"
    assert report_exhausted.checks["github_tokens"].status == "error"


@pytest.mark.anyio
async def test_health_routes_via_http(tmp_path: Path) -> None:
    server = create_mcp_server()
    settings = Settings(
        raw_dir=tmp_path / "raw",
        canonical_dir=tmp_path / "canonical",
        output_dir=tmp_path / "output",
    )
    app = get_streamable_http_app(server, settings=settings)

    routes = [r.path for r in app.routes if isinstance(r, Route)]
    assert "/healthz" in routes
    assert "/readyz" in routes
    assert "/metrics" in routes

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Liveness probe
        res_live = await client.get("/healthz")
        assert res_live.status_code == 200
        assert res_live.json() == {"status": "ok"}

        # Readiness probe
        res_ready = await client.get("/readyz")
        assert res_ready.status_code == 200
        data = res_ready.json()
        assert data["status"] == "ok"
        assert "checks" in data
        assert data["checks"]["raw_storage"]["status"] == "ok"

        # Prometheus metrics endpoint
        res_metrics = await client.get("/metrics")
        assert res_metrics.status_code == 200
        assert "# HELP" in res_metrics.text
