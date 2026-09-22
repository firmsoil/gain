from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from gain.storage.checkpoint import CheckpointStore


def test_checkpoint_default_state(tmp_path: Path) -> None:
    store = CheckpointStore(tmp_path / "checkpoints")
    state = store.load("run-123", "acme/repo1")

    assert state == {"repository": "acme/repo1", "next_page": 1, "cursor": None}


def test_checkpoint_sharded_save_and_load(tmp_path: Path) -> None:
    root = tmp_path / "checkpoints"
    store = CheckpointStore(root)
    run_id = "run-shard-01"
    repo = "firmsoil/spinnaker"
    payload: dict[str, Any] = {"repository": repo, "next_page": 5, "cursor": "cursor_xyz"}

    store.save(run_id, repo, payload)

    # Verify physical file location
    sharded_file = root / run_id / "firmsoil__spinnaker.json"
    assert sharded_file.exists()
    assert not (root / run_id / "firmsoil__spinnaker.tmp").exists()

    # Load and verify content
    loaded = store.load(run_id, repo)
    assert loaded == payload


def test_checkpoint_atomic_replacement(tmp_path: Path) -> None:
    root = tmp_path / "checkpoints"
    store = CheckpointStore(root)
    run_id = "run-atomic"
    repo = "firmsoil/gain"

    store.save(run_id, repo, {"repository": repo, "next_page": 2, "cursor": "c1"})
    loaded1 = store.load(run_id, repo)
    assert loaded1["next_page"] == 2

    # Overwrite state atomically
    store.save(run_id, repo, {"repository": repo, "next_page": 3, "cursor": "c2"})
    loaded2 = store.load(run_id, repo)
    assert loaded2["next_page"] == 3
    assert loaded2["cursor"] == "c2"

    # No leftover .tmp files
    tmp_files = list((root / run_id).glob("*.tmp"))
    assert tmp_files == []


def test_checkpoint_fallback_to_legacy(tmp_path: Path) -> None:
    root = tmp_path / "checkpoints"
    root.mkdir(parents=True, exist_ok=True)
    run_id = "run-legacy-01"

    # Write a monolithic legacy checkpoint file
    legacy_file = root / f"{run_id}__checkpoint.json"
    legacy_data = {
        "acme/service-a": {"repository": "acme/service-a", "next_page": 4, "cursor": "cur-a"},
        "acme/service-b": {"repository": "acme/service-b", "next_page": 2, "cursor": "cur-b"},
    }
    legacy_file.write_text(json.dumps(legacy_data, indent=2), encoding="utf-8")

    store = CheckpointStore(root)

    # Should successfully load from legacy file
    loaded_a = store.load(run_id, "acme/service-a")
    assert loaded_a["next_page"] == 4
    assert loaded_a["cursor"] == "cur-a"

    # Unrecorded repo in legacy file should return default state
    loaded_c = store.load(run_id, "acme/service-c")
    assert loaded_c == {"repository": "acme/service-c", "next_page": 1, "cursor": None}

    # If sharded checkpoint is subsequently saved, sharded takes precedence over legacy
    store.save(
        run_id,
        "acme/service-a",
        {"repository": "acme/service-a", "next_page": 10, "cursor": "cur-new"},
    )
    loaded_sharded_a = store.load(run_id, "acme/service-a")
    assert loaded_sharded_a["next_page"] == 10
    assert loaded_sharded_a["cursor"] == "cur-new"

    # service-b should still be read from legacy file
    loaded_b = store.load(run_id, "acme/service-b")
    assert loaded_b["next_page"] == 2


def test_list_checkpoints(tmp_path: Path) -> None:
    root = tmp_path / "checkpoints"
    store = CheckpointStore(root)
    run_id = "run-list-01"

    # Initially empty
    assert store.list_checkpoints(run_id) == {}

    # Seed legacy file with repo-1 and repo-2
    legacy_file = root / f"{run_id}__checkpoint.json"
    legacy_data = {
        "org/repo-1": {"repository": "org/repo-1", "next_page": 2, "cursor": "c1"},
        "org/repo-2": {"repository": "org/repo-2", "next_page": 3, "cursor": "c2"},
    }
    legacy_file.write_text(json.dumps(legacy_data, indent=2), encoding="utf-8")

    # Add sharded for repo-2 (override) and repo-3 (new)
    store.save(
        run_id, "org/repo-2", {"repository": "org/repo-2", "next_page": 5, "cursor": "c2-updated"}
    )
    store.save(run_id, "org/repo-3", {"repository": "org/repo-3", "next_page": 1, "cursor": None})

    all_checkpoints = store.list_checkpoints(run_id)
    assert len(all_checkpoints) == 3
    assert all_checkpoints["org/repo-1"]["next_page"] == 2
    assert all_checkpoints["org/repo-2"]["next_page"] == 5
    assert all_checkpoints["org/repo-2"]["cursor"] == "c2-updated"
    assert all_checkpoints["org/repo-3"]["next_page"] == 1
