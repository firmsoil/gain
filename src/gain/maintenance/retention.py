from __future__ import annotations

import shutil
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger(__name__)


def purge_old_raw_runs(
    raw_dir: Path,
    older_than_days: int = 90,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Purge raw JSONL ingestion runs older than a retention threshold.

    Preserves checkpoints directory and only targets ingestion run folders.
    """
    cutoff_epoch = time.time() - (older_than_days * 86400)
    cutoff_dt = datetime.fromtimestamp(cutoff_epoch, tz=UTC)

    purged_runs: list[str] = []
    purged_bytes: int = 0
    purged_files: int = 0

    if not raw_dir.exists():
        return {
            "older_than_days": older_than_days,
            "cutoff_timestamp": cutoff_dt.isoformat(),
            "dry_run": dry_run,
            "purged_runs": [],
            "purged_bytes": 0,
            "purged_files": 0,
        }

    for run_path in sorted(raw_dir.iterdir()):
        if not run_path.is_dir() or run_path.name == "checkpoints":
            continue

        mtime = run_path.stat().st_mtime
        if mtime < cutoff_epoch:
            run_bytes = sum(f.stat().st_size for f in run_path.rglob("*") if f.is_file())
            run_files = sum(1 for f in run_path.rglob("*") if f.is_file())

            purged_runs.append(run_path.name)
            purged_bytes += run_bytes
            purged_files += run_files

            if not dry_run:
                shutil.rmtree(run_path)
                log.info("raw_run_purged", run_id=run_path.name, bytes=run_bytes, files=run_files)
            else:
                log.info(
                    "raw_run_purge_dry_run", run_id=run_path.name, bytes=run_bytes, files=run_files
                )

    return {
        "older_than_days": older_than_days,
        "cutoff_timestamp": cutoff_dt.isoformat(),
        "dry_run": dry_run,
        "purged_runs": purged_runs,
        "purged_bytes": purged_bytes,
        "purged_files": purged_files,
    }


def purge_old_checkpoints(
    checkpoint_dir: Path,
    older_than_days: int = 30,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Purge sharded and legacy checkpoints older than a retention threshold."""
    cutoff_epoch = time.time() - (older_than_days * 86400)
    cutoff_dt = datetime.fromtimestamp(cutoff_epoch, tz=UTC)

    purged_items: list[str] = []
    purged_bytes: int = 0

    if not checkpoint_dir.exists():
        return {
            "older_than_days": older_than_days,
            "cutoff_timestamp": cutoff_dt.isoformat(),
            "dry_run": dry_run,
            "purged_items": [],
            "purged_bytes": 0,
        }

    for item in sorted(checkpoint_dir.iterdir()):
        mtime = item.stat().st_mtime
        if mtime < cutoff_epoch:
            if item.is_dir():
                item_bytes = sum(f.stat().st_size for f in item.rglob("*") if f.is_file())
                purged_items.append(item.name)
                purged_bytes += item_bytes
                if not dry_run:
                    shutil.rmtree(item)
            elif item.is_file():
                item_bytes = item.stat().st_size
                purged_items.append(item.name)
                purged_bytes += item_bytes
                if not dry_run:
                    item.unlink()

    return {
        "older_than_days": older_than_days,
        "cutoff_timestamp": cutoff_dt.isoformat(),
        "dry_run": dry_run,
        "purged_items": purged_items,
        "purged_bytes": purged_bytes,
    }
