from __future__ import annotations

import uuid
from pathlib import Path

import polars as pl
import structlog

log = structlog.get_logger(__name__)


class CompactionService:
    """Merges small Parquet files in partition directories into target row-group files."""

    def __init__(
        self,
        target_file_size_bytes: int = 128 * 1024 * 1024,
        small_file_threshold_bytes: int | None = None,
        min_file_count: int = 2,
        row_group_size: int | None = None,
    ) -> None:
        self.target_file_size_bytes = target_file_size_bytes
        self.small_file_threshold_bytes = (
            small_file_threshold_bytes
            if small_file_threshold_bytes is not None
            else target_file_size_bytes
        )
        self.min_file_count = min_file_count
        self.row_group_size = row_group_size

    def compact_partition(self, partition_dir: Path) -> Path | None:
        """Compact small Parquet files in a partition directory into a single compacted file."""
        if not partition_dir.exists() or not partition_dir.is_dir():
            return None

        parquet_files = sorted(f for f in partition_dir.glob("*.parquet") if f.is_file())
        small_files = [
            f for f in parquet_files if f.stat().st_size < self.small_file_threshold_bytes
        ]
        if len(small_files) < self.min_file_count:
            return None

        lock_file = partition_dir / ".compaction.lock"
        if lock_file.exists():
            log.info("compaction_skipped_locked", partition_dir=str(partition_dir))
            return None

        try:
            lock_file.touch(exist_ok=False)
        except FileExistsError:
            return None

        try:
            return self._do_compact(partition_dir, small_files, lock_file)
        finally:
            if lock_file.exists():
                lock_file.unlink(missing_ok=True)

    def _do_compact(
        self, partition_dir: Path, small_files: list[Path], lock_file: Path
    ) -> Path | None:

        try:
            dfs = [pl.read_parquet(f) for f in small_files]
            merged_df = pl.concat(dfs, how="diagonal_relaxed")
        except Exception as exc:
            log.error(
                "compaction_read_error",
                partition_dir=str(partition_dir),
                exc_info=exc,
            )
            raise

        compact_id = uuid.uuid4().hex[:12]
        tmp_file = partition_dir / f"compact_{compact_id}.tmp"
        target_file = partition_dir / f"compacted_{compact_id}.parquet"

        try:
            if self.row_group_size is not None:
                merged_df.write_parquet(tmp_file, row_group_size=self.row_group_size)
            else:
                merged_df.write_parquet(tmp_file)
            tmp_file.replace(target_file)
        except Exception as exc:
            if tmp_file.exists():
                tmp_file.unlink(missing_ok=True)
            log.error("compaction_write_error", tmp_file=str(tmp_file), exc_info=exc)
            raise

        # Atomically remove old small files
        for f in small_files:
            if f != target_file:
                f.unlink(missing_ok=True)

        log.info(
            "compaction_finished",
            partition_dir=str(partition_dir),
            compacted_file=str(target_file),
            row_count=merged_df.height,
        )
        return target_file

    def compact_all(self, root_dir: Path) -> list[Path]:
        """Recursively scan and compact all partition directories containing Parquet files."""
        if not root_dir.exists() or not root_dir.is_dir():
            return []

        partition_dirs: set[Path] = {p.parent for p in root_dir.rglob("*.parquet") if p.is_file()}
        compacted: list[Path] = []
        for pdir in sorted(partition_dirs):
            res = self.compact_partition(pdir)
            if res is not None:
                compacted.append(res)

        return compacted
