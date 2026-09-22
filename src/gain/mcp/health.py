from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from pydantic import BaseModel, ConfigDict
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from gain.config import Settings, get_settings
from gain.github.token_pool import GitHubTokenPool

log = structlog.get_logger(__name__)


class CheckDetail(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: str  # "ok", "degraded", "error"
    message: str | None = None
    details: dict[str, Any] | None = None


class ReadinessReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: str  # "ok", "degraded", "unhealthy"
    version: str = "0.1.0"
    timestamp: datetime
    checks: dict[str, CheckDetail]


def check_liveness() -> dict[str, str]:
    """Basic liveness probe indicating the process is alive and responsive."""
    return {"status": "ok"}


def _check_storage_writable(directory: Path) -> CheckDetail:
    """Check if a directory exists and is writable."""
    try:
        directory.mkdir(parents=True, exist_ok=True)
        test_file = directory / f".write_test_{datetime.now(UTC).timestamp()}"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink()
        return CheckDetail(status="ok", details={"path": str(directory), "writable": True})
    except Exception as exc:
        log.error("storage_health_check_failed", directory=str(directory), exc_info=exc)
        return CheckDetail(
            status="error",
            message=f"Storage directory not writable: {exc}",
            details={"path": str(directory), "writable": False},
        )


def _check_token_pool(token_pool: GitHubTokenPool | None) -> CheckDetail:
    """Check GitHub authentication and token pool quota."""
    if token_pool is None or len(token_pool) == 0:
        return CheckDetail(
            status="ok",
            message="No token pool attached (PAT or mock fallback).",
            details={"configured": False},
        )

    exhausted_count = sum(1 for p in token_pool.providers if p.is_exhausted())
    total_count = len(token_pool)

    if exhausted_count == total_count:
        return CheckDetail(
            status="error",
            message="All tokens in pool are rate-limited or exhausted.",
            details={
                "total_tokens": total_count,
                "exhausted_tokens": exhausted_count,
                "available_tokens": 0,
            },
        )
    elif exhausted_count > 0:
        return CheckDetail(
            status="degraded",
            message=f"{exhausted_count}/{total_count} tokens currently rate-limited.",
            details={
                "total_tokens": total_count,
                "exhausted_tokens": exhausted_count,
                "available_tokens": total_count - exhausted_count,
            },
        )
    return CheckDetail(
        status="ok",
        details={
            "total_tokens": total_count,
            "exhausted_tokens": 0,
            "available_tokens": total_count,
        },
    )


def check_readiness(
    settings: Settings | None = None,
    token_pool: GitHubTokenPool | None = None,
) -> ReadinessReport:
    """Comprehensive readiness probe verifying storage and auth readiness."""
    active_settings = settings or get_settings()

    checks: dict[str, CheckDetail] = {}

    # Check raw_dir
    checks["raw_storage"] = _check_storage_writable(active_settings.raw_dir)

    # Check canonical_dir
    checks["canonical_storage"] = _check_storage_writable(active_settings.canonical_dir)

    # Check token pool
    checks["github_tokens"] = _check_token_pool(token_pool)

    # Determine overall status
    has_error = any(c.status == "error" for c in checks.values())
    has_degraded = any(c.status == "degraded" for c in checks.values())

    if has_error:
        overall_status = "unhealthy"
    elif has_degraded:
        overall_status = "degraded"
    else:
        overall_status = "ok"

    return ReadinessReport(
        status=overall_status,
        version="0.1.0",
        timestamp=datetime.now(UTC),
        checks=checks,
    )


async def liveness_endpoint(request: Request) -> JSONResponse:
    """Handler for GET /healthz (liveness probe)."""
    return JSONResponse(check_liveness(), status_code=200)


def create_readiness_endpoint(
    settings: Settings | None = None,
    token_pool: GitHubTokenPool | None = None,
) -> Any:
    """Create a readiness handler closure with injected settings and token pool."""

    async def readiness_endpoint(request: Request) -> JSONResponse:
        report = check_readiness(settings=settings, token_pool=token_pool)
        status_code = 503 if report.status == "unhealthy" else 200
        return JSONResponse(report.model_dump(mode="json"), status_code=status_code)

    return readiness_endpoint


async def metrics_endpoint(request: Request) -> Response:
    """Handler for GET /metrics (Prometheus metrics exposition)."""
    from gain.telemetry.metrics import REGISTRY

    return Response(
        content=REGISTRY.to_prometheus_format(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
        status_code=200,
    )


def add_health_endpoints(
    app: Starlette,
    *,
    settings: Settings | None = None,
    token_pool: GitHubTokenPool | None = None,
) -> None:
    """Attach /healthz, /readyz, and /metrics routes to a Starlette application."""
    routes = [
        Route("/healthz", endpoint=liveness_endpoint, methods=["GET"]),
        Route(
            "/readyz",
            endpoint=create_readiness_endpoint(settings=settings, token_pool=token_pool),
            methods=["GET"],
        ),
        Route("/metrics", endpoint=metrics_endpoint, methods=["GET"]),
    ]
    for route in routes:
        app.routes.append(route)
    log.info("health_endpoints_registered", endpoints=["/healthz", "/readyz", "/metrics"])
