from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class RawStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def append_page(
        self,
        *,
        ingestion_run_id: str,
        owner: str,
        name: str,
        page_number: int,
        cursor: str | None,
        repository_id: str,
        repository_name_with_owner: str,
        nodes: list[dict[str, Any]],
    ) -> Path:
        run_dir = self.root / ingestion_run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / f"{owner}__{name}__page-{page_number:05d}.jsonl"
        collected_at = datetime.now(UTC).isoformat()
        metadata = {
            "ingestion_run_id": ingestion_run_id,
            "owner": owner,
            "name": name,
            "page_number": page_number,
            "cursor": cursor,
            "repository_id": repository_id,
            "repository_name_with_owner": repository_name_with_owner,
            "collected_at": collected_at,
        }
        with path.open("w", encoding="utf-8") as handle:
            for node in nodes:
                handle.write(json.dumps({"metadata": metadata, "node": node}, sort_keys=True))
                handle.write("\n")
        return path

    def read_run(self, ingestion_run_id: str) -> list[dict[str, Any]]:
        run_dir = self.root / ingestion_run_id
        records: list[dict[str, Any]] = []
        for path in sorted(run_dir.glob("*.jsonl")):
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    records.append(json.loads(line))
        return records
