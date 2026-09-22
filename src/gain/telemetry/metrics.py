from __future__ import annotations

import threading
import time
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import structlog

log = structlog.get_logger(__name__)


class Counter:
    def __init__(self, name: str, description: str, labels: tuple[str, ...] = ()) -> None:
        self.name = name
        self.description = description
        self.label_names = labels
        self._values: dict[tuple[str, ...], float] = defaultdict(float)
        self._lock = threading.Lock()

    def inc(self, amount: float = 1.0, **labels: str) -> None:
        key = tuple(labels.get(lbl, "") for lbl in self.label_names)
        with self._lock:
            self._values[key] += amount

    def get(self, **labels: str) -> float:
        key = tuple(labels.get(lbl, "") for lbl in self.label_names)
        with self._lock:
            return self._values[key]

    def collect(self) -> list[tuple[dict[str, str], float]]:
        with self._lock:
            result = []
            for key, val in self._values.items():
                lbl_dict = dict(zip(self.label_names, key, strict=False))
                result.append((lbl_dict, val))
            return result


class Gauge:
    def __init__(self, name: str, description: str, labels: tuple[str, ...] = ()) -> None:
        self.name = name
        self.description = description
        self.label_names = labels
        self._values: dict[tuple[str, ...], float] = {}
        self._lock = threading.Lock()

    def set(self, value: float, **labels: str) -> None:
        key = tuple(labels.get(lbl, "") for lbl in self.label_names)
        with self._lock:
            self._values[key] = value

    def get(self, **labels: str) -> float | None:
        key = tuple(labels.get(lbl, "") for lbl in self.label_names)
        with self._lock:
            return self._values.get(key)

    def collect(self) -> list[tuple[dict[str, str], float]]:
        with self._lock:
            result = []
            for key, val in self._values.items():
                lbl_dict = dict(zip(self.label_names, key, strict=False))
                result.append((lbl_dict, val))
            return result


class Histogram:
    DEFAULT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

    def __init__(
        self,
        name: str,
        description: str,
        labels: tuple[str, ...] = (),
        buckets: tuple[float, ...] | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.label_names = labels
        self.buckets = buckets or self.DEFAULT_BUCKETS
        self._counts: dict[tuple[str, ...], int] = defaultdict(int)
        self._sums: dict[tuple[str, ...], float] = defaultdict(float)
        self._bucket_counts: dict[tuple[str, ...], dict[float, int]] = defaultdict(
            lambda: {b: 0 for b in self.buckets}
        )
        self._lock = threading.Lock()

    def observe(self, value: float, **labels: str) -> None:
        key = tuple(labels.get(lbl, "") for lbl in self.label_names)
        with self._lock:
            self._counts[key] += 1
            self._sums[key] += value
            b_counts = self._bucket_counts[key]
            for b in self.buckets:
                if value <= b:
                    b_counts[b] += 1

    @contextmanager
    def time(self, **labels: str) -> Iterator[None]:
        start = time.monotonic()
        try:
            yield
        finally:
            self.observe(time.monotonic() - start, **labels)

    def get_summary(self, **labels: str) -> dict[str, Any]:
        key = tuple(labels.get(lbl, "") for lbl in self.label_names)
        with self._lock:
            return {
                "count": self._counts[key],
                "sum": self._sums[key],
                "buckets": dict(self._bucket_counts[key]),
            }


class TelemetryRegistry:
    def __init__(self) -> None:
        self._metrics: dict[str, Counter | Gauge | Histogram] = {}
        self._lock = threading.Lock()

    def register_counter(
        self, name: str, description: str, labels: tuple[str, ...] = ()
    ) -> Counter:
        with self._lock:
            if name not in self._metrics:
                self._metrics[name] = Counter(name, description, labels)
            return self._metrics[name]  # type: ignore[return-value]

    def register_gauge(self, name: str, description: str, labels: tuple[str, ...] = ()) -> Gauge:
        with self._lock:
            if name not in self._metrics:
                self._metrics[name] = Gauge(name, description, labels)
            return self._metrics[name]  # type: ignore[return-value]

    def register_histogram(
        self,
        name: str,
        description: str,
        labels: tuple[str, ...] = (),
        buckets: tuple[float, ...] | None = None,
    ) -> Histogram:
        with self._lock:
            if name not in self._metrics:
                self._metrics[name] = Histogram(name, description, labels, buckets)
            return self._metrics[name]  # type: ignore[return-value]

    def to_prometheus_format(self) -> str:
        lines: list[str] = []
        with self._lock:
            for name, metric in sorted(self._metrics.items()):
                lines.append(f"# HELP {name} {metric.description}")
                type_str = (
                    "counter"
                    if isinstance(metric, Counter)
                    else "gauge"
                    if isinstance(metric, Gauge)
                    else "histogram"
                )
                lines.append(f"# TYPE {name} {type_str}")

                if isinstance(metric, (Counter, Gauge)):
                    for labels, val in metric.collect():
                        if labels:
                            lbl_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
                            lines.append(f"{name}{{{lbl_str}}} {val}")
                        else:
                            lines.append(f"{name} {val}")
                elif isinstance(metric, Histogram):
                    for key, count in metric._counts.items():
                        lbl_dict = dict(zip(metric.label_names, key, strict=False))
                        b_counts = metric._bucket_counts[key]
                        for b in metric.buckets:
                            b_labels = dict(lbl_dict)
                            b_labels["le"] = str(b)
                            lbl_str = ",".join(f'{k}="{v}"' for k, v in sorted(b_labels.items()))
                            lines.append(f"{name}_bucket{{{lbl_str}}} {b_counts[b]}")
                        # +Inf bucket
                        inf_labels = dict(lbl_dict)
                        inf_labels["le"] = "+Inf"
                        inf_str = ",".join(f'{k}="{v}"' for k, v in sorted(inf_labels.items()))
                        lines.append(f"{name}_bucket{{{inf_str}}} {count}")

                        base_lbl_str = (
                            "{" + ",".join(f'{k}="{v}"' for k, v in sorted(lbl_dict.items())) + "}"
                            if lbl_dict
                            else ""
                        )
                        lines.append(f"{name}_count{base_lbl_str} {count}")
                        lines.append(f"{name}_sum{base_lbl_str} {metric._sums[key]}")
        return "\n".join(lines) + "\n"


# Global telemetry registry and standardized metric definitions
REGISTRY = TelemetryRegistry()

# Ingestion metrics
INGESTION_PAGES_TOTAL = REGISTRY.register_counter(
    "gain_ingestion_pages_total",
    "Total pull request GraphQL pages successfully fetched and persisted.",
    labels=("repository", "run_id"),
)

INGESTION_NODES_TOTAL = REGISTRY.register_counter(
    "gain_ingestion_nodes_total",
    "Total pull request node entities captured in window.",
    labels=("repository", "run_id"),
)

INGESTION_DURATION_SECONDS = REGISTRY.register_histogram(
    "gain_ingestion_duration_seconds",
    "Time taken to ingest repository pull request pages in seconds.",
    labels=("repository",),
)

GITHUB_RATE_LIMIT_REMAINING = REGISTRY.register_gauge(
    "gain_github_rate_limit_remaining",
    "Remaining GitHub GraphQL API rate limit quota.",
    labels=("token_id", "org"),
)

MCP_REQUESTS_TOTAL = REGISTRY.register_counter(
    "gain_mcp_requests_total",
    "Total requests serviced by GAIN MCP Server.",
    labels=("tool_name", "status"),
)

MCP_REQUEST_DURATION_SECONDS = REGISTRY.register_histogram(
    "gain_mcp_request_duration_seconds",
    "Latency of GAIN MCP tool and resource evaluations in seconds.",
    labels=("tool_name",),
)
