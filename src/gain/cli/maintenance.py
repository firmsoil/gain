from __future__ import annotations

import json

import typer

from gain.config import get_settings
from gain.logging import configure_logging


def register_maintenance_commands(maintenance_app: typer.Typer) -> None:
    @maintenance_app.command("stats")
    def maintenance_stats() -> None:
        """Show storage disk usage breakdown across GAIN directories."""
        from gain.maintenance.stats import compute_storage_stats

        settings = get_settings()
        stats = compute_storage_stats(settings.data_dir)
        typer.echo(json.dumps(stats, indent=2, sort_keys=True))

    @maintenance_app.command("purge-raw")
    def maintenance_purge_raw(
        days: int = typer.Option(90, "--days", "-d", help="Purge raw runs older than N days."),
        dry_run: bool = typer.Option(
            False, "--dry-run", help="Report runs that would be purged without deleting."
        ),
    ) -> None:
        """Purge raw JSONL ingestion runs older than a retention period."""
        configure_logging()
        from gain.maintenance.retention import purge_old_raw_runs

        settings = get_settings()
        result = purge_old_raw_runs(settings.raw_dir, older_than_days=days, dry_run=dry_run)
        typer.echo(json.dumps(result, indent=2, sort_keys=True))

    @maintenance_app.command("purge-checkpoints")
    def maintenance_purge_checkpoints(
        days: int = typer.Option(30, "--days", "-d", help="Purge checkpoints older than N days."),
        dry_run: bool = typer.Option(
            False, "--dry-run", help="Report checkpoints that would be purged without deleting."
        ),
    ) -> None:
        """Purge checkpoint directories and legacy files older than a retention period."""
        configure_logging()
        from gain.maintenance.retention import purge_old_checkpoints

        settings = get_settings()
        checkpoint_dir = settings.raw_dir / "checkpoints"
        result = purge_old_checkpoints(checkpoint_dir, older_than_days=days, dry_run=dry_run)
        typer.echo(json.dumps(result, indent=2, sort_keys=True))

    @maintenance_app.command("compact")
    def maintenance_compact(
        execute: bool = typer.Option(
            False, "--execute", help="Execute compaction (default is dry-run)."
        ),
        target_size_mb: int = typer.Option(
            128, "--target-size-mb", help="Target Parquet file size in MB."
        ),
    ) -> None:
        """Consolidate fragmented Parquet partition files into optimal row-group files."""
        configure_logging()
        from gain.storage.compaction import CompactionService

        settings = get_settings()
        service = CompactionService(
            target_file_size_bytes=target_size_mb * 1024 * 1024,
        )
        if not execute:
            partition_dirs = {
                p.parent for p in settings.canonical_dir.rglob("*.parquet") if p.is_file()
            }
            candidates = []
            for pdir in sorted(partition_dirs):
                parquet_files = [f for f in pdir.glob("*.parquet") if f.is_file()]
                small = [
                    f
                    for f in parquet_files
                    if f.stat().st_size < service.small_file_threshold_bytes
                ]
                if len(small) >= service.min_file_count:
                    candidates.append({"partition": str(pdir), "small_files": len(small)})
            result = {"execute": False, "dry_run": True, "partitions_to_compact": candidates}
        else:
            compacted = service.compact_all(settings.canonical_dir)
            result = {"execute": True, "compacted_files": [str(f) for f in compacted]}
        typer.echo(json.dumps(result, indent=2, sort_keys=True))
