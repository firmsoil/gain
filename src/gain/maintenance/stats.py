from __future__ import annotations

from pathlib import Path
from typing import Any


def _format_bytes(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024.0 or unit == "TB":
            return f"{size:.2f} {unit}"
        size /= 1024.0  # type: ignore[assignment]
    return f"{size} B"


def compute_storage_stats(root_data_dir: Path) -> dict[str, Any]:
    """Compute comprehensive storage footprint breakdown across GAIN data directories."""
    subdirs = ["raw", "canonical", "output", "raw/checkpoints"]
    breakdown: dict[str, dict[str, Any]] = {}
    total_bytes = 0
    total_files = 0

    if not root_data_dir.exists():
        return {
            "root": str(root_data_dir),
            "total_bytes": 0,
            "total_files": 0,
            "total_formatted": "0.00 B",
            "breakdown": {},
        }

    for sub in subdirs:
        target = root_data_dir / sub
        if not target.exists():
            breakdown[sub] = {"bytes": 0, "files": 0, "formatted": "0.00 B"}
            continue

        size = sum(f.stat().st_size for f in target.rglob("*") if f.is_file())
        count = sum(1 for f in target.rglob("*") if f.is_file())
        breakdown[sub] = {"bytes": size, "files": count, "formatted": _format_bytes(size)}
        if sub != "raw/checkpoints":  # Avoid double-counting inside raw
            total_bytes += size
            total_files += count

    return {
        "root": str(root_data_dir),
        "total_bytes": total_bytes,
        "total_files": total_files,
        "total_formatted": _format_bytes(total_bytes),
        "breakdown": breakdown,
    }
