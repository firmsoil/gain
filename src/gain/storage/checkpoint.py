from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger(__name__)


class CheckpointStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _sharded_path(self, run_id: str, repository: str) -> Path:
        safe_name = repository.replace("/", "__")
        return self.root / run_id / f"{safe_name}.json"

    def _legacy_path(self, run_id: str) -> Path:
        return self.root / f"{run_id}__checkpoint.json"

    def load(self, run_id: str, repository: str) -> dict[str, Any]:
        default_state: dict[str, Any] = {"repository": repository, "next_page": 1, "cursor": None}
        sharded_path = self._sharded_path(run_id, repository)
        if sharded_path.exists():
            try:
                data = json.loads(sharded_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return dict(data)
            except Exception as exc:
                log.warning("sharded_checkpoint_read_error", path=str(sharded_path), exc_info=exc)

        legacy_path = self._legacy_path(run_id)
        if legacy_path.exists():
            try:
                legacy_data = json.loads(legacy_path.read_text(encoding="utf-8"))
                if isinstance(legacy_data, dict):
                    repo_data = legacy_data.get(repository)
                    if isinstance(repo_data, dict):
                        return dict(repo_data)
            except Exception as exc:
                log.warning("legacy_checkpoint_read_error", path=str(legacy_path), exc_info=exc)

        return default_state

    def save(self, run_id: str, repository: str, state: dict[str, Any]) -> None:
        path = self._sharded_path(run_id, repository)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(f"{path.stem}_{uuid.uuid4().hex[:8]}.tmp")
        tmp_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
        tmp_path.replace(path)

    def list_checkpoints(self, run_id: str) -> dict[str, dict[str, Any]]:
        """Inspect all checkpoints for a given run ID."""
        results: dict[str, dict[str, Any]] = {}

        legacy_path = self._legacy_path(run_id)
        if legacy_path.exists():
            try:
                legacy_data = json.loads(legacy_path.read_text(encoding="utf-8"))
                if isinstance(legacy_data, dict):
                    for repo_key, repo_state in legacy_data.items():
                        if isinstance(repo_state, dict):
                            results[repo_key] = dict(repo_state)
            except Exception as exc:
                log.warning("legacy_checkpoint_list_error", path=str(legacy_path), exc_info=exc)

        run_dir = self.root / run_id
        if run_dir.exists() and run_dir.is_dir():
            for file in sorted(run_dir.glob("*.json")):
                try:
                    data = json.loads(file.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        repo = str(data.get("repository") or file.stem.replace("__", "/"))
                        results[repo] = dict(data)
                except Exception as exc:
                    log.warning("sharded_checkpoint_list_error", path=str(file), exc_info=exc)
                    continue

        return results
