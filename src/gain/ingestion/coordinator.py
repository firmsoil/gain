from __future__ import annotations

import asyncio
import contextlib
import signal
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
import structlog

from gain.config import Settings
from gain.github.async_client import AsyncGitHubGraphQLClient
from gain.github.token_pool import GitHubTokenPool
from gain.ingestion.queue import InProcessQueue, WorkItem, WorkQueue, create_work_queue
from gain.ingestion.worker import IngestionWorker
from gain.registry import RepositoryRegistry
from gain.storage.checkpoint import CheckpointStore
from gain.storage.raw import RawStore

log = structlog.get_logger(__name__)


class IngestionCoordinator:
    """Coordinates fan-out multi-worker distributed pull request ingestion."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        token_pool: GitHubTokenPool | None = None,
        registry: RepositoryRegistry | None = None,
        queue: WorkQueue | None = None,
        num_workers: int = 1,
        batch_size: int = 50,
        org: str | None = None,
        tier: str | None = None,
        raw_store: RawStore | None = None,
        checkpoint_store: CheckpointStore | None = None,
        client: AsyncGitHubGraphQLClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.registry = registry
        if queue is not None:
            self.queue = queue
        elif settings is not None:
            self.queue = create_work_queue(
                backend=settings.queue_backend, redis_url=settings.redis_url
            )
        else:
            self.queue = InProcessQueue()
        self.num_workers = max(1, num_workers)
        self.batch_size = batch_size
        self.org = org
        self.tier = tier
        self.client = client
        self.transport = transport

        if token_pool is not None:
            self.token_pool: GitHubTokenPool | None = token_pool
        elif settings is not None and (settings.github_token or settings.github_app_id):
            self.token_pool = GitHubTokenPool.from_settings(settings)
        else:
            self.token_pool = None

        if raw_store is not None:
            self.raw_store = raw_store
        elif settings is not None:
            self.raw_store = RawStore(settings.raw_dir)
        else:
            self.raw_store = RawStore(Path("data/raw"))

        if checkpoint_store is not None:
            self.checkpoint_store = checkpoint_store
        elif settings is not None:
            self.checkpoint_store = CheckpointStore(settings.raw_dir / "checkpoints")
        else:
            self.checkpoint_store = CheckpointStore(Path("data/raw/checkpoints"))

        self._workers: list[IngestionWorker] = []
        self._shutdown_requested: bool = False

    @property
    def shutdown_requested(self) -> bool:
        return self._shutdown_requested

    def get_target_repositories(self) -> list[tuple[str, str]]:
        """Determine repository list and tiers from registry or settings."""
        repos: list[tuple[str, str]] = []
        if self.registry is not None and self.registry.count() > 0:
            entries = self.registry.list_all()
            if self.org is not None:
                org_filter = self.org.strip().lower()
                entries = [e for e in entries if e.org_id.strip().lower() == org_filter]
            if self.tier is not None:
                tier_filter = self.tier.strip().lower()
                entries = [e for e in entries if e.tier.strip().lower() == tier_filter]
            repos = [(e.name_with_owner, e.tier) for e in entries if not e.is_archived]
        elif self.settings is not None and self.settings.github_repos:
            default_tier = self.tier or "standard"
            repos = [(repo, default_tier) for repo in self.settings.github_repos]
        return repos

    def request_shutdown(self) -> None:
        """Signal all workers and the coordinator to finish current page and drain."""
        self._shutdown_requested = True
        log.info("coordinator_shutdown_requested", active_workers=len(self._workers))
        for worker in self._workers:
            worker.request_shutdown()

    async def run(self, run_id: str | None = None) -> dict[str, Any]:
        """Execute distributed backfill run across spawned workers."""
        active_run_id = run_id or str(uuid.uuid4())
        start_time = time.monotonic()
        self._shutdown_requested = False

        if self.settings is not None:
            self.settings.ensure_directories()

        target_repos = self.get_target_repositories()
        log.info(
            "coordinator_starting",
            run_id=active_run_id,
            target_repos_count=len(target_repos),
            num_workers=self.num_workers,
        )

        for repo, tier in target_repos:
            item = WorkItem(repository=repo, run_id=active_run_id, tier=tier)
            await self.queue.enqueue(item)

        self._workers = [
            IngestionWorker(
                worker_id=f"worker-{i}",
                token_pool=self.token_pool,
                settings=self.settings,
                client=self.client,
                raw_store=self.raw_store,
                checkpoint_store=self.checkpoint_store,
                page_size=self.batch_size,
                transport=self.transport,
            )
            for i in range(self.num_workers)
        ]

        loop = asyncio.get_running_loop()
        signals = (signal.SIGTERM, signal.SIGINT)

        def _sig_handler() -> None:
            log.info("coordinator_signal_received")
            self.request_shutdown()

        for sig in signals:
            with contextlib.suppress(NotImplementedError, RuntimeError, ValueError):
                loop.add_signal_handler(sig, _sig_handler)

        try:
            tasks = [asyncio.create_task(w.run(self.queue)) for w in self._workers]
            worker_results = await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            for sig in signals:
                with contextlib.suppress(NotImplementedError, RuntimeError, ValueError):
                    loop.remove_signal_handler(sig)

        duration_seconds = time.monotonic() - start_time

        pages_fetched = 0
        nodes_captured = 0
        repositories_processed = 0

        for r in worker_results:
            if isinstance(r, dict):
                pages_fetched += int(r.get("pages_fetched", 0))
                nodes_captured += int(r.get("nodes_captured", 0))
                repositories_processed += int(r.get("repositories_processed", 0))
            elif isinstance(r, Exception):
                log.error("worker_crashed_with_exception", error=str(r))

        failed_queue_items = getattr(self.queue, "failed", [])
        task_exceptions = [r for r in worker_results if isinstance(r, Exception)]
        failures = len(failed_queue_items) + len(task_exceptions)

        totals: dict[str, Any] = {
            "run_id": active_run_id,
            "repositories_processed": repositories_processed,
            "pages_fetched": pages_fetched,
            "nodes_captured": nodes_captured,
            "failures": failures,
            "duration_seconds": round(duration_seconds, 3),
        }

        if self._shutdown_requested:
            totals["shutdown_requested"] = True

        log.info("coordinator_completed", **totals)
        return totals
