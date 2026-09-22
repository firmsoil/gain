"""Inverted index mapping entity identifiers to storage locations for fast lookups."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from gain.config import get_settings
from gain.storage.analytics import read_canonical

log = structlog.get_logger(__name__)


def _normalize_entity_type(entity_type: str) -> str:
    """Normalize entity type aliases to canonical category keys."""
    norm = entity_type.strip().lower()
    if norm in ("pr", "pull_request", "pullrequest", "pull_requests"):
        return "pr"
    if norm in ("issue", "issues", "work_item", "work_items"):
        return "issue"
    if norm in ("commit", "commits"):
        return "commit"
    if norm in ("deployment", "deployments", "deploy"):
        return "deployment"
    if norm in ("raw", "raw_pr", "raw_record", "raw_records"):
        return "raw"
    return norm


def _extract_identifiers(record: dict[str, Any], identifier_key: str | None = None) -> set[str]:
    """Extract candidate identifiers from a record dictionary."""
    identifiers: set[str] = set()

    if identifier_key and identifier_key in record and record[identifier_key] is not None:
        identifiers.add(str(record[identifier_key]))
        return identifiers

    # Known top-level fields
    for field in (
        "identifier",
        "github_node_id",
        "issue_key",
        "key",
        "pr_number",
        "number",
        "commit_sha",
        "sha",
        "deployment_id",
        "id",
    ):
        val = record.get(field)
        if val is not None:
            identifiers.add(str(val))

    # Nested GraphQL 'node' field
    node = record.get("node")
    if isinstance(node, dict):
        if node.get("id") is not None:
            identifiers.add(str(node["id"]))
        if node.get("number") is not None:
            identifiers.add(str(node["number"]))

    # Fallback: scan for any string/int field ending in _id or _key
    if not identifiers:
        for k, v in record.items():
            if (
                (k.endswith("_id") or k.endswith("_key") or k in ("id", "name"))
                and v is not None
                and isinstance(v, (str, int))
            ):
                identifiers.add(str(v))

    return identifiers


class EntityIndex:
    """Inverted index mapping entity identifiers to storage locations and metadata."""

    def __init__(self, index_dir: Path | str | None = None) -> None:
        if index_dir is not None:
            self.index_dir = Path(index_dir)
        else:
            settings = get_settings()
            idx_dir = settings.indexes_dir
            if idx_dir != Path("./data/indexes"):
                self.index_dir = idx_dir
            elif settings.output_dir != Path("./data"):
                self.index_dir = settings.output_dir / "indexes"
            else:
                self.index_dir = idx_dir

        self.index_file = self.index_dir / "entity_index.json"
        self._index: dict[str, dict[str, dict[str, Any]]] = {}
        self.load()

    def load(self) -> None:
        """Load the inverted index from disk if present."""
        if not self.index_file.exists():
            return
        try:
            with self.index_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    self._index = data
        except Exception as exc:
            log.warning("entity_index_load_failed", path=str(self.index_file), exc_info=exc)

    def save(self) -> None:
        """Atomically persist the inverted index to disk."""
        self.index_dir.mkdir(parents=True, exist_ok=True)
        tmp_file = self.index_file.with_suffix(".tmp")
        try:
            with tmp_file.open("w", encoding="utf-8") as f:
                json.dump(self._index, f, indent=2, default=str)
            tmp_file.replace(self.index_file)
        except Exception as exc:
            log.error("entity_index_save_failed", path=str(self.index_file), exc_info=exc)
            if tmp_file.exists():
                tmp_file.unlink(missing_ok=True)
            raise

    def index_entity(
        self,
        entity_type: str,
        identifier: str,
        location: str | Path,
        metadata: dict[str, Any] | None = None,
        auto_save: bool = True,
    ) -> None:
        """Index a single entity by its identifier and storage location."""
        norm_type = _normalize_entity_type(entity_type)
        entry: dict[str, Any] = {
            "entity_type": norm_type,
            "identifier": str(identifier),
            "location": str(location),
        }
        if metadata:
            for k, v in metadata.items():
                if isinstance(v, (datetime, Path)):
                    entry[k] = str(v)
                else:
                    entry[k] = v

        if norm_type not in self._index:
            self._index[norm_type] = {}
        self._index[norm_type][str(identifier)] = entry

        if auto_save:
            self.save()

    def index_records(
        self,
        entity_type: str,
        records: list[dict[str, Any]],
        location: str | Path,
        identifier_key: str | None = None,
    ) -> None:
        """Index a batch of entity records located at a given storage location."""
        norm_type = _normalize_entity_type(entity_type)

        for record in records:
            identifiers = _extract_identifiers(record, identifier_key=identifier_key)

            # Build metadata dict excluding raw nested payloads
            meta: dict[str, Any] = {}
            for k, v in record.items():
                if k == "node" and isinstance(v, dict):
                    for nk, nv in v.items():
                        if nk not in meta and isinstance(nv, (str, int, float, bool, type(None))):
                            meta[nk] = nv
                elif isinstance(v, (str, int, float, bool, type(None), list, dict)):
                    meta[k] = v
                elif isinstance(v, (datetime, Path)):
                    meta[k] = str(v)

            for ident in identifiers:
                self.index_entity(
                    entity_type=norm_type,
                    identifier=ident,
                    location=location,
                    metadata=meta,
                    auto_save=False,
                )

        self.save()

    def lookup(self, entity_type: str, identifier: str) -> dict[str, Any] | None:
        """Look up an entity by type and identifier.

        Returns matching metadata dict with 'location', or None if not indexed.
        """
        ident_str = str(identifier)
        norm_type = _normalize_entity_type(entity_type)

        # Check in-memory index
        category = self._index.get(norm_type)
        if category and ident_str in category:
            return dict(category[ident_str])

        # Check raw entity type key if different
        raw_cat = self._index.get(entity_type.lower())
        if raw_cat and ident_str in raw_cat:
            return dict(raw_cat[ident_str])

        # If not found and file exists, reload once in case external update occurred
        if self.index_file.exists() and not self._index:
            self.load()
            cat = self._index.get(norm_type)
            if cat and ident_str in cat:
                return dict(cat[ident_str])

        return None

    def clear(self) -> None:
        """Clear all indexed entries and remove persistent index file."""
        self._index.clear()
        if self.index_file.exists():
            self.index_file.unlink(missing_ok=True)

    def contains(self, entity_type: str, identifier: str) -> bool:
        """Return True if the entity is present in the index."""
        return self.lookup(entity_type, identifier) is not None

    def count(self, entity_type: str | None = None) -> int:
        """Return total number of indexed entries, optionally filtered by type."""
        if entity_type is None:
            return sum(len(sub) for sub in self._index.values())
        return len(self._index.get(_normalize_entity_type(entity_type), {}))

    def index_canonical_prs(self, canonical_dir: Path | None = None) -> int:
        """Scan canonical Parquet files and index all PR records."""
        target_dir = canonical_dir or get_settings().canonical_dir
        if not target_dir.exists():
            return 0

        total_indexed = 0
        for file_path in sorted(target_dir.glob("*.parquet")):
            try:
                prs = read_canonical(file_path)
                records = [pr.to_record() for pr in prs]
                self.index_records("pr", records, str(file_path))
                total_indexed += len(records)
            except Exception as exc:
                log.warning("index_canonical_file_failed", path=str(file_path), exc_info=exc)

        return total_indexed

    def index_raw_prs(self, raw_dir: Path | None = None) -> int:
        """Scan raw JSONL files and index all raw PR records with line numbers."""
        target_dir = raw_dir or get_settings().raw_dir
        if not target_dir.exists():
            return 0

        total_indexed = 0
        for raw_file in sorted(target_dir.glob("*.jsonl")):
            try:
                records: list[dict[str, Any]] = []
                with raw_file.open("r", encoding="utf-8") as f:
                    for line_idx, line in enumerate(f, start=1):
                        line_str = line.strip()
                        if not line_str:
                            continue
                        rec = json.loads(line_str)
                        rec["line_number"] = line_idx
                        rec["raw_file"] = raw_file.name
                        records.append(rec)
                if records:
                    self.index_records("raw", records, str(raw_file))
                    total_indexed += len(records)
            except Exception as exc:
                log.warning("index_raw_file_failed", path=str(raw_file), exc_info=exc)

        return total_indexed
