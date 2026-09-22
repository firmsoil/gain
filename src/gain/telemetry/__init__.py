from __future__ import annotations

from gain.telemetry.metrics import (
    GITHUB_RATE_LIMIT_REMAINING,
    INGESTION_DURATION_SECONDS,
    INGESTION_NODES_TOTAL,
    INGESTION_PAGES_TOTAL,
    MCP_REQUEST_DURATION_SECONDS,
    MCP_REQUESTS_TOTAL,
    REGISTRY,
    Counter,
    Gauge,
    Histogram,
    TelemetryRegistry,
)
from gain.telemetry.tracing import Span, trace_span

__all__ = [
    "GITHUB_RATE_LIMIT_REMAINING",
    "INGESTION_DURATION_SECONDS",
    "INGESTION_NODES_TOTAL",
    "INGESTION_PAGES_TOTAL",
    "MCP_REQUEST_DURATION_SECONDS",
    "MCP_REQUESTS_TOTAL",
    "REGISTRY",
    "Counter",
    "Gauge",
    "Histogram",
    "Span",
    "TelemetryRegistry",
    "trace_span",
]
