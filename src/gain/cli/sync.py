from __future__ import annotations

import json
import uuid

import structlog
import typer

from gain.cli.common import _build_client
from gain.config import get_settings
from gain.logging import configure_logging
from gain.quality import validate_pull_requests
from gain.registry import RepositoryRegistry
from gain.schema import normalize_records
from gain.storage.analytics import write_canonical
from gain.storage.raw import RawStore
from gain.sync import PullRequestBackfill


def register_sync_commands(app: typer.Typer) -> None:
    @app.command("config-check")
    def config_check() -> None:
        """Validate runtime configuration without contacting GitHub."""
        configure_logging()
        settings = get_settings()
        settings.validate_runtime()
        typer.echo("GAIN configuration OK")
        typer.echo(f"repositories={','.join(settings.github_repos)}")
        typer.echo(f"window={settings.start_at.isoformat()}..{settings.end_at.isoformat()}")

    @app.command()
    def backfill() -> None:
        """Backfill PRs from GitHub GraphQL into replayable raw storage."""
        configure_logging()
        settings = get_settings()
        settings.validate_runtime()
        settings.ensure_directories()
        run_id = str(uuid.uuid4())
        structlog.contextvars.bind_contextvars(run_id=run_id)
        result = PullRequestBackfill(settings, _build_client(settings)).run(ingestion_run_id=run_id)
        typer.echo(json.dumps(result, indent=2, sort_keys=True))

    @app.command("sync")
    def sync(
        workers: int = typer.Option(
            1,
            "--workers",
            "-w",
            help="Number of concurrent worker tasks (if > 1 uses IngestionCoordinator).",
        ),
        batch_size: int = typer.Option(
            50,
            "--batch-size",
            "-b",
            help="Batch size for GraphQL pagination.",
        ),
        tier: str | None = typer.Option(
            None,
            "--tier",
            help="Filter registry repositories by tier (e.g. critical, standard, archive).",
        ),
        run_id: str | None = typer.Option(
            None,
            "--run-id",
            help="Ingestion run ID under raw directory (defaults to auto-generated UUID).",
        ),
    ) -> None:
        """Synchronize pull requests from GitHub into raw storage (single or multi-worker)."""
        import asyncio

        from gain.ingestion.coordinator import IngestionCoordinator

        configure_logging()
        settings = get_settings()
        settings.validate_runtime()
        settings.ensure_directories()
        active_run_id = run_id or str(uuid.uuid4())
        structlog.contextvars.bind_contextvars(run_id=active_run_id)

        registry = (
            RepositoryRegistry(settings.registry_path) if settings.registry_path.exists() else None
        )

        if workers > 1:
            coordinator = IngestionCoordinator(
                settings=settings,
                registry=registry,
                num_workers=workers,
                batch_size=batch_size,
                tier=tier,
            )
            result = asyncio.run(coordinator.run(run_id=active_run_id))
        else:
            sync_settings = settings
            if tier is not None and registry is not None and registry.count() > 0:
                tier_entries = registry.list_by_tier(tier)
                target_repos = [e.name_with_owner for e in tier_entries if not e.is_archived]
                sync_settings = sync_settings.model_copy(
                    update={"github_repos": target_repos, "page_size": batch_size}
                )
            elif batch_size != sync_settings.page_size:
                sync_settings = sync_settings.model_copy(update={"page_size": batch_size})

            result = PullRequestBackfill(sync_settings, _build_client(sync_settings)).run(
                ingestion_run_id=active_run_id
            )

        typer.echo(json.dumps(result, indent=2, sort_keys=True))

    @app.command()
    def normalize(
        run_id: str = typer.Option(..., help="Ingestion run ID under the raw directory."),
    ) -> None:
        """Normalize a raw ingestion run into the canonical PR dataset."""
        configure_logging()
        structlog.contextvars.bind_contextvars(run_id=run_id)
        settings = get_settings()
        settings.ensure_directories()
        raw_records = RawStore(settings.raw_dir).read_run(run_id)
        prs, errors = normalize_records(raw_records)
        quality_issues = validate_pull_requests(prs)
        canonical_path = settings.canonical_dir / f"pull_requests__{run_id}.parquet"
        write_canonical(prs, canonical_path)
        report = {
            "run_id": run_id,
            "raw_records": len(raw_records),
            "canonical_records": len(prs),
            "normalization_errors": errors,
            "quality_issues": [issue.__dict__ for issue in quality_issues],
            "canonical_path": str(canonical_path),
        }
        report_path = settings.output_dir / f"normalization_report__{run_id}.json"
        report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        typer.echo(json.dumps(report, indent=2, default=str))
