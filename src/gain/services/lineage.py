"""Domain service for end-to-end data lineage and provenance traversal."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from gain.config import Settings, get_settings
from gain.model.pr import PullRequest
from gain.storage.analytics import read_canonical


@dataclass(frozen=True)
class LineageNode:
    layer: str  # "raw", "canonical", "metric_observation"
    identifier: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class LineageTrace:
    target_id: str
    target_type: str
    nodes: list[LineageNode]
    provenance_chain: list[str]


class LineageService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def get_pr_lineage(self, github_node_id: str) -> LineageTrace | None:
        canonical_dir = self.settings.canonical_dir
        if not canonical_dir.exists():
            return None

        matched_pr: PullRequest | None = None
        canonical_file: str | None = None

        for path in sorted(canonical_dir.glob("*.parquet")):
            try:
                prs = read_canonical(path)
                for pr in prs:
                    if pr.github_node_id == github_node_id:
                        matched_pr = pr
                        canonical_file = path.name
                        break
            except Exception:
                continue
            if matched_pr:
                break

        if not matched_pr:
            return None

        nodes: list[LineageNode] = []
        provenance_chain: list[str] = []

        # 1. Raw Node Lookup
        raw_dir = self.settings.raw_dir
        raw_meta: dict[str, Any] = {
            "ingestion_run_id": matched_pr.ingestion_run_id,
            "collected_at": matched_pr.collected_at.isoformat(),
            "repository": matched_pr.repository_name_with_owner,
        }

        # Attempt to inspect raw jsonl files if present
        for raw_file in sorted(raw_dir.glob("*.jsonl")):
            try:
                with raw_file.open(encoding="utf-8") as f:
                    for line_idx, line in enumerate(f, start=1):
                        record = json.loads(line)
                        node = record.get("node", {})
                        if node.get("id") == github_node_id:
                            raw_meta["raw_file"] = raw_file.name
                            raw_meta["line_number"] = line_idx
                            raw_meta["cursor"] = record.get("cursor")
                            raw_meta["page_number"] = record.get("page_number")
                            break
            except Exception:
                continue
            if "raw_file" in raw_meta:
                break

        raw_node_id = f"raw:{matched_pr.ingestion_run_id}:{github_node_id}"
        nodes.append(LineageNode(layer="raw", identifier=raw_node_id, metadata=raw_meta))
        provenance_chain.append(raw_node_id)

        # 2. Canonical Node
        canonical_node_id = f"canonical:pr:{github_node_id}"
        nodes.append(
            LineageNode(
                layer="canonical",
                identifier=canonical_node_id,
                metadata={
                    "file": canonical_file,
                    "repository": matched_pr.repository_name_with_owner,
                    "number": matched_pr.number,
                    "state": matched_pr.state,
                    "created_at": matched_pr.created_at.isoformat(),
                    "merged_at": matched_pr.merged_at.isoformat() if matched_pr.merged_at else None,
                },
            )
        )
        provenance_chain.append(canonical_node_id)

        # 3. Metric Observation Node
        if matched_pr.merged_at:
            metric_node_id = f"metric:GAIN-PR-001:1:{github_node_id}"
            cycle_time = matched_pr.cycle_time_seconds()
            nodes.append(
                LineageNode(
                    layer="metric_observation",
                    identifier=metric_node_id,
                    metadata={
                        "metric_id": "GAIN-PR-001",
                        "metric_version": 1,
                        "cycle_time_seconds": cycle_time,
                    },
                )
            )
            provenance_chain.append(metric_node_id)

        return LineageTrace(
            target_id=github_node_id,
            target_type="PullRequest",
            nodes=nodes,
            provenance_chain=provenance_chain,
        )
