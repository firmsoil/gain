"""Telemetry and structured logging for GAIN MCP requests."""

from __future__ import annotations

import time
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import structlog

logger = structlog.get_logger("gain.mcp")


@contextmanager
def trace_mcp_request(
    operation_type: str,  # "tool", "resource", "prompt"
    operation_name: str,
    principal: str,
    tenant: str,
    extra: dict[str, Any] | None = None,
) -> Generator[dict[str, Any], None, None]:
    request_id = f"mcp-{uuid.uuid4().hex[:10]}"
    start_time = time.monotonic()
    context: dict[str, Any] = {
        "request_id": request_id,
        "operation_type": operation_type,
        "operation_name": operation_name,
        "principal": principal,
        "tenant": tenant,
    }
    if extra:
        context.update(extra)

    logger.info("mcp_request_started", **context)
    try:
        yield context
        duration_ms = round((time.monotonic() - start_time) * 1000, 2)
        logger.info(
            "mcp_request_completed",
            duration_ms=duration_ms,
            status="SUCCESS",
            **context,
        )
    except Exception as exc:
        duration_ms = round((time.monotonic() - start_time) * 1000, 2)
        error_type = type(exc).__name__
        logger.error(
            "mcp_request_failed",
            duration_ms=duration_ms,
            status="ERROR",
            error_type=error_type,
            error_message=str(exc),
            **context,
        )
        raise
