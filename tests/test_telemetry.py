from __future__ import annotations

import time

from gain.telemetry.metrics import (
    Counter,
    Gauge,
    Histogram,
    TelemetryRegistry,
)
from gain.telemetry.tracing import trace_span


def test_telemetry_counter() -> None:
    counter = Counter("test_counter", "Test counter description", labels=("repo", "tier"))
    assert counter.get(repo="acme/gain", tier="critical") == 0.0

    counter.inc(1.0, repo="acme/gain", tier="critical")
    counter.inc(2.5, repo="acme/gain", tier="critical")
    assert counter.get(repo="acme/gain", tier="critical") == 3.5

    collected = counter.collect()
    assert len(collected) == 1
    assert collected[0] == ({"repo": "acme/gain", "tier": "critical"}, 3.5)


def test_telemetry_gauge() -> None:
    gauge = Gauge("test_gauge", "Test gauge description", labels=("pool",))
    assert gauge.get(pool="primary") is None

    gauge.set(4950.0, pool="primary")
    assert gauge.get(pool="primary") == 4950.0

    gauge.set(4900.0, pool="primary")
    assert gauge.get(pool="primary") == 4900.0


def test_telemetry_histogram() -> None:
    hist = Histogram(
        "test_latency_seconds",
        "Test latency",
        labels=("service",),
        buckets=(0.01, 0.05, 0.1, 1.0),
    )

    with hist.time(service="github"):
        time.sleep(0.002)

    hist.observe(0.04, service="github")

    summary = hist.get_summary(service="github")
    assert summary["count"] == 2
    assert summary["sum"] > 0
    assert summary["buckets"][0.05] >= 1


def test_telemetry_registry_prometheus_format() -> None:
    reg = TelemetryRegistry()
    c = reg.register_counter("http_requests_total", "Total requests", labels=("method",))
    g = reg.register_gauge("memory_usage_bytes", "Memory usage")
    h = reg.register_histogram("response_time_seconds", "Latency", buckets=(0.1, 1.0))

    c.inc(10, method="GET")
    g.set(1048576)
    h.observe(0.05)

    prom_text = reg.to_prometheus_format()
    assert "# HELP http_requests_total Total requests" in prom_text
    assert "# TYPE http_requests_total counter" in prom_text
    assert 'http_requests_total{method="GET"} 10.0' in prom_text
    assert "# TYPE memory_usage_bytes gauge" in prom_text
    assert "memory_usage_bytes 1048576" in prom_text
    assert "# TYPE response_time_seconds histogram" in prom_text
    assert 'response_time_seconds_bucket{le="0.1"} 1' in prom_text
    assert "response_time_seconds_count 1" in prom_text


def test_trace_span() -> None:
    with trace_span("ingest_repository", repo="acme/gain") as span:
        assert span.name == "ingest_repository"
        assert span.attributes["repo"] == "acme/gain"
        span.set_attribute("pages", 5)
        assert span.attributes["pages"] == 5
    assert span.end_time is not None
    assert span.status == "ok"


def test_trace_span_error_recording() -> None:
    try:
        with trace_span("failing_operation") as span:
            raise ValueError("Test failure")
    except ValueError:
        pass

    assert span.status == "error"
    assert span.attributes["error.type"] == "ValueError"
    assert span.attributes["error.message"] == "Test failure"
