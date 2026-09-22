from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from gain.cli import app
from gain.config import Settings
from gain.maintenance.retention import purge_old_checkpoints, purge_old_raw_runs
from gain.maintenance.stats import compute_storage_stats

runner = CliRunner()


def test_compute_storage_stats(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    raw_dir = data_dir / "raw"
    canonical_dir = data_dir / "canonical"
    checkpoints_dir = raw_dir / "checkpoints"

    raw_dir.mkdir(parents=True)
    canonical_dir.mkdir(parents=True)
    checkpoints_dir.mkdir(parents=True)

    # Write files
    (raw_dir / "run-1" / "file.jsonl").parent.mkdir()
    (raw_dir / "run-1" / "file.jsonl").write_text('{"a": 1}\n')
    (canonical_dir / "pr.parquet").write_text("dummy-parquet")
    (checkpoints_dir / "chk1.json").write_text('{"page": 1}')

    stats = compute_storage_stats(data_dir)
    assert stats["total_files"] >= 2
    assert stats["total_bytes"] > 0
    assert "raw" in stats["breakdown"]
    assert "canonical" in stats["breakdown"]


def test_purge_old_raw_runs(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    old_run = raw_dir / "old-run-2025"
    new_run = raw_dir / "new-run-2026"
    checkpoints = raw_dir / "checkpoints"

    old_run.mkdir(parents=True)
    new_run.mkdir(parents=True)
    checkpoints.mkdir(parents=True)

    (old_run / "data.jsonl").write_text("old")
    (new_run / "data.jsonl").write_text("new")
    (checkpoints / "chk.json").write_text("chk")

    # Set old_run mtime to 100 days ago
    old_time = time.time() - (100 * 86400)
    import os

    os.utime(old_run, (old_time, old_time))

    # Dry run
    res_dry = purge_old_raw_runs(raw_dir, older_than_days=90, dry_run=True)
    assert res_dry["dry_run"] is True
    assert "old-run-2025" in res_dry["purged_runs"]
    assert old_run.exists()

    # Execute run
    res_exec = purge_old_raw_runs(raw_dir, older_than_days=90, dry_run=False)
    assert res_exec["dry_run"] is False
    assert "old-run-2025" in res_exec["purged_runs"]
    assert not old_run.exists()
    assert new_run.exists()
    assert checkpoints.exists()


def test_purge_old_checkpoints(tmp_path: Path) -> None:
    chk_dir = tmp_path / "checkpoints"
    chk_dir.mkdir(parents=True)

    old_chk = chk_dir / "old_repo.json"
    new_chk = chk_dir / "new_repo.json"
    old_chk.write_text("{}")
    new_chk.write_text("{}")

    old_time = time.time() - (45 * 86400)
    import os

    os.utime(old_chk, (old_time, old_time))

    # Purge older than 30 days
    res = purge_old_checkpoints(chk_dir, older_than_days=30, dry_run=False)
    assert "old_repo.json" in res["purged_items"]
    assert not old_chk.exists()
    assert new_chk.exists()


def test_cli_maintenance_stats(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        raw_dir=tmp_path / "data" / "raw",
        canonical_dir=tmp_path / "data" / "canonical",
        output_dir=tmp_path / "data" / "output",
    )
    monkeypatch.setattr("gain.cli.get_settings", lambda: settings)

    result = runner.invoke(app, ["maintenance", "stats"])
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert "total_bytes" in parsed
    assert "breakdown" in parsed


def test_cli_maintenance_help() -> None:
    result = runner.invoke(app, ["maintenance", "--help"])
    assert result.exit_code == 0
    assert "purge-raw" in result.stdout
    assert "purge-checkpoints" in result.stdout
    assert "compact" in result.stdout
    assert "stats" in result.stdout
