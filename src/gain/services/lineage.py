"""Domain service for end-to-end data lineage and provenance traversal."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

from gain.config import Settings, get_settings
from gain.model.pr import PullRequest
from gain.storage.analytics import read_canonical
from gain.storage.index import EntityIndex
from gain.storage.relationships import RelationshipStore

log = structlog.get_logger(__name__)


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
    def __init__(
        self,
        settings: Settings | None = None,
        index: EntityIndex | None = None,
        relationships: RelationshipStore | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        index_dir = self._resolve_index_dir()
        self.index = index if index is not None else EntityIndex(index_dir=index_dir)
        self.relationships = (
            relationships if relationships is not None else RelationshipStore(storage_dir=index_dir)
        )

    def _resolve_index_dir(self) -> Path:
        idx_dir = getattr(self.settings, "indexes_dir", None)
        if isinstance(idx_dir, Path) and idx_dir != Path("./data/indexes"):
            return idx_dir
        if self.settings.output_dir != Path("./data"):
            return self.settings.output_dir / "indexes"
        if isinstance(idx_dir, Path):
            return idx_dir
        return Path("./data/indexes")

    def get_pr_lineage(self, github_node_id: str) -> LineageTrace | None:
        """Trace data lineage for a pull request from raw payload to metric observation."""
        canonical_dir = self.settings.canonical_dir
        if not canonical_dir.exists():
            return None

        matched_pr: PullRequest | None = None
        canonical_file: str | None = None

        # 1. Fast indexed canonical lookup
        if self.index:
            entry = self.index.lookup("pr", github_node_id)
            if entry and "location" in entry:
                loc = entry["location"]
                target_path = Path(loc)
                if not target_path.is_absolute() and not target_path.exists():
                    target_path = canonical_dir / target_path
                if target_path.exists():
                    try:
                        prs = read_canonical(target_path)
                        for pr in prs:
                            if pr.github_node_id == github_node_id:
                                matched_pr = pr
                                canonical_file = target_path.name
                                break
                    except Exception as exc:
                        log.warning(
                            "lineage_index_file_read_failed",
                            file_path=str(target_path),
                            exc_info=exc,
                        )

        # 2. Fallback to scanning all canonical files if not found via index
        if not matched_pr:
            for path in sorted(canonical_dir.glob("*.parquet")):
                try:
                    prs = read_canonical(path)
                    for pr in prs:
                        if pr.github_node_id == github_node_id:
                            matched_pr = pr
                            canonical_file = path.name
                            break
                except (FileNotFoundError, json.JSONDecodeError, Exception) as exc:
                    log.warning("lineage_file_skipped", file_path=str(path), exc_info=exc)
                    continue
                if matched_pr:
                    break

        if not matched_pr:
            return None

        nodes: list[LineageNode] = []
        provenance_chain: list[str] = []

        # 3. Raw Node Lookup (fast indexed lookup first, fallback to jsonl scan)
        raw_dir = self.settings.raw_dir
        raw_meta: dict[str, Any] = {
            "ingestion_run_id": matched_pr.ingestion_run_id,
            "collected_at": matched_pr.collected_at.isoformat(),
            "repository": matched_pr.repository_name_with_owner,
        }

        if self.index:
            raw_entry = self.index.lookup("raw", github_node_id)
            if raw_entry:
                loc = raw_entry.get("location")
                if loc:
                    raw_meta["raw_file"] = Path(loc).name
                if "line_number" in raw_entry:
                    raw_meta["line_number"] = raw_entry["line_number"]
                if "cursor" in raw_entry:
                    raw_meta["cursor"] = raw_entry["cursor"]
                if "page_number" in raw_entry:
                    raw_meta["page_number"] = raw_entry["page_number"]

        # Attempt to inspect raw jsonl files if present and not resolved by index
        if "raw_file" not in raw_meta and raw_dir.exists():
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
                except (FileNotFoundError, json.JSONDecodeError, Exception) as exc:
                    log.warning("lineage_file_skipped", file_path=str(raw_file), exc_info=exc)
                    continue
                if "raw_file" in raw_meta:
                    break

        raw_node_id = f"raw:{matched_pr.ingestion_run_id}:{github_node_id}"
        nodes.append(LineageNode(layer="raw", identifier=raw_node_id, metadata=raw_meta))
        provenance_chain.append(raw_node_id)

        # 4. Canonical Node
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

        # 5. Metric Observation Node
        if matched_pr.merged_at:
            metric_node_id = f"metric:GAIN-PR-001:1:{github_node_id}"
            cycle_time = (matched_pr.merged_at - matched_pr.created_at).total_seconds()
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

    def get_pr_linked_issues(self, repository: str, pr_number: int) -> list[str]:
        """Return issue keys linked to a given pull request."""
        return self.relationships.get_linked_issues(repository, pr_number)

    def get_issue_linked_prs(self, issue_key: str) -> list[dict[str, Any]]:
        """Return pull request references linked to a given issue."""
        return self.relationships.get_linked_prs(issue_key)
