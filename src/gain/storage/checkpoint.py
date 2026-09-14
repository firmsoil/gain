from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class CheckpointStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def load(self, ingestion_run_id: str, repository: str) -> dict[str, Any]:
        path = self.root / f"{ingestion_run_id}__checkpoint.json"
        if not path.exists():
            return {"repository": repository, "next_page": 1, "cursor": None}
        data = json.loads(path.read_text(encoding="utf-8"))
        return dict(data.get(repository, {"repository": repository, "next_page": 1, "cursor": None}))

    def save(self, ingestion_run_id: str, repository: str, state: dict[str, Any]) -> None:
        path = self.root / f"{ingestion_run_id}__checkpoint.json"
        all_state: dict[str, Any] = {}
        if path.exists():
            all_state = json.loads(path.read_text(encoding="utf-8"))
        all_state[repository] = state
        path.write_text(json.dumps(all_state, indent=2, sort_keys=True), encoding="utf-8")
