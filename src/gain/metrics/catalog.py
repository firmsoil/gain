from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class MetricCatalog:
    def __init__(self, path: Path) -> None:
        self.path = path
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or "version" not in payload or "metrics" not in payload:
            raise ValueError("Invalid Metric Catalog")
        self.version = int(payload["version"])
        self.metrics: dict[str, dict[str, Any]] = {}
        for metric in payload["metrics"]:
            metric_id = str(metric["metric_id"])
            if metric_id in self.metrics:
                raise ValueError(f"Duplicate metric ID: {metric_id}")
            self.metrics[metric_id] = dict(metric)

    def get(self, metric_id: str) -> dict[str, Any]:
        return self.metrics[metric_id]
