from __future__ import annotations

import asyncio
import contextlib
import signal
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import structlog

from gain.config import Settings, get_settings
from gain.errors import ConfigurationError, RateLimitError
from gain.github.async_client import AsyncGitHubGraphQLClient
from gain.github.auth import GitHubAuth
from gain.github.token_pool import GitHubTokenPool
from gain.ingestion.queue import WorkItem, WorkQueue
from gain.storage.checkpoint import CheckpointStore
from gain.storage.raw import RawStore
from gain.telemetry.metrics import (
    INGESTION_DURATION_SECONDS,
    INGESTION_NODES_TOTAL,
    INGESTION_PAGES_TOTAL,
)
from gain.util import parse_utc_datetime

log = structlog.get_logger(__name__)


class IngestionWorker:
    """Worker task that consumes work items and ingests PR pages asynchronously."""

    def __init__(
        self,
        worker_id: str = "worker-0",
        *,
        token_pool: GitHubTokenPool | None = None,
        settings: Settings | None = None,
        client: AsyncGitHubGraphQLClient | None = None,
        raw_store: RawStore | None = None,
        checkpoint_store: CheckpointStore | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        page_size: int | None = None,
        max_retries: int | None = None,
        base_backoff_seconds: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.worker_id = worker_id
        self.shutdown_requested: bool = False
        self.token_pool = token_pool

        if settings is not None:
            self.settings: Settings | None = settings
            self.raw_store = raw_store or RawStore(settings.raw_dir)
            self.checkpoint_store = checkpoint_store or CheckpointStore(
                settings.raw_dir / "checkpoints"
            )
            self.start_at = start_at or settings.start_at
            self.end_at = end_at or settings.end_at
            self.page_size = page_size or settings.page_size
            self.max_retries = max_retries if max_retries is not None else settings.max_retries
            self.base_backoff_seconds = (
                base_backoff_seconds
                if base_backoff_seconds is not None
                else settings.base_backoff_seconds
            )
            self.api_url = settings.github_api_url
        else:
            self.settings = None
            if raw_store is None or checkpoint_store is None:
                try:
                    s = get_settings()
                    self.settings = s
                    self.raw_store = raw_store or RawStore(s.raw_dir)
                    self.checkpoint_store = checkpoint_store or CheckpointStore(
                        s.raw_dir / "checkpoints"
                    )
                    self.start_at = start_at or s.start_at
                    self.end_at = end_at or s.end_at
                    self.page_size = page_size or s.page_size
                    self.max_retries = max_retries if max_retries is not None else s.max_retries
                    self.base_backoff_seconds = (
                        base_backoff_seconds
                        if base_backoff_seconds is not None
                        else s.base_backoff_seconds
                    )
                    self.api_url = s.github_api_url
                except Exception:
                    self.raw_store = raw_store or RawStore(Path("data/raw"))
                    self.checkpoint_store = checkpoint_store or CheckpointStore(
                        Path("data/raw/checkpoints")
                    )
                    self.start_at = start_at or datetime(1970, 1, 1, tzinfo=UTC)
                    self.end_at = end_at or datetime(2099, 1, 1, tzinfo=UTC)
                    self.page_size = page_size or 50
                    self.max_retries = max_retries if max_retries is not None else 4
                    self.base_backoff_seconds = (
                        base_backoff_seconds if base_backoff_seconds is not None else 1.0
                    )
                    self.api_url = "https://api.github.com/graphql"
            else:
                self.raw_store = raw_store
                self.checkpoint_store = checkpoint_store
                self.start_at = start_at or datetime(1970, 1, 1, tzinfo=UTC)
                self.end_at = end_at or datetime(2099, 1, 1, tzinfo=UTC)
                self.page_size = page_size or 50
                self.max_retries = max_retries if max_retries is not None else 4
                self.base_backoff_seconds = (
                    base_backoff_seconds if base_backoff_seconds is not None else 1.0
                )
                self.api_url = "https://api.github.com/graphql"

        self.transport = transport
        if client is not None:
            self._client: AsyncGitHubGraphQLClient | None = client
            self._owns_client = False
            if self.transport is None:
                self.transport = client.transport
        else:
            self._client = None
            self._owns_client = True

    @property
    def client(self) -> AsyncGitHubGraphQLClient | None:
        return self._client

    def request_shutdown(self) -> None:
        """Signal that worker should stop cleanly after saving current page's checkpoint."""
        self.shutdown_requested = True
        log.info("worker_shutdown_requested", worker_id=self.worker_id)

    def _get_or_create_client(self, org: str | None = None) -> AsyncGitHubGraphQLClient:
        if self._client is not None and not self._client.is_closed:
            return self._client

        if self.token_pool is not None and len(self.token_pool) > 0:
            auth = self.token_pool.acquire_token(org=org)
            client = AsyncGitHubGraphQLClient(
                auth=auth,
                api_url=self.api_url,
                page_size=self.page_size,
                max_retries=self.max_retries,
                base_backoff_seconds=self.base_backoff_seconds,
                transport=self.transport,
            )
            self._client = client
            self._owns_client = True
            return client

        if self.settings is not None and self.settings.github_token:
            client = AsyncGitHubGraphQLClient(
                token=self.settings.github_token,
                api_url=self.api_url,
                page_size=self.page_size,
                max_retries=self.max_retries,
                base_backoff_seconds=self.base_backoff_seconds,
                transport=self.transport,
            )
            self._client = client
            self._owns_client = True
            return client

        raise ConfigurationError("No GitHub authentication configured for IngestionWorker")

    def _can_rotate_token(self, org: str | None = None) -> bool:
        if self.token_pool is None or len(self.token_pool) <= 1:
            return False
        current_auth = getattr(self._client, "_auth", None)
        return any(
            not p.is_exhausted()
            for p in self.token_pool.providers
            if (org is None or p.org is None or p.org == org) and (p is not current_auth)
        )

    def _rotate_token(
        self, org: str | None = None, reset_epoch: float | None = None
    ) -> AsyncGitHubGraphQLClient:
        if self.token_pool is None:
            raise RateLimitError("Cannot rotate token: no token pool available")

        if self._client is not None:
            current_auth = getattr(self._client, "_auth", None)
            if isinstance(current_auth, GitHubAuth):
                reset_time = reset_epoch if reset_epoch is not None else (time.time() + 60.0)
                self.token_pool.report_rate_limit(
                    current_auth,
                    remaining=0,
                    reset_epoch=reset_time,
                )
                log.warning(
                    "worker_token_exhausted_reported",
                    worker_id=self.worker_id,
                    token=current_auth.name,
                    reset_time=reset_time,
                )

        new_auth = self.token_pool.acquire_token(org=org)
        log.info(
            "worker_token_rotated",
            worker_id=self.worker_id,
            new_token=new_auth.name,
        )

        new_client = AsyncGitHubGraphQLClient(
            auth=new_auth,
            api_url=self.api_url,
            page_size=self.page_size,
            max_retries=self.max_retries,
            base_backoff_seconds=self.base_backoff_seconds,
            transport=self.transport,
        )
        self._client = new_client
        self._owns_client = True
        return new_client

    def _in_window(self, node: dict[str, Any]) -> bool:
        created_raw = node.get("createdAt")
        if not isinstance(created_raw, str):
            return False
        created = parse_utc_datetime(created_raw)
        return self.start_at <= created <= self.end_at

    async def process_item(self, item: WorkItem) -> dict[str, Any]:
        """Process a single repository WorkItem across pages."""
        if self.shutdown_requested:
            log.info("worker_shutdown_before_item", worker_id=self.worker_id, repo=item.repository)
            return {
                "repository": item.repository,
                "pages": 0,
                "nodes": 0,
                "completed": False,
            }

        checkpoint = self.checkpoint_store.load(item.run_id, item.repository)
        page_number = int(checkpoint.get("next_page", 1))
        cursor: str | None = checkpoint.get("cursor")
        owner, name = item.repository.split("/", 1)
        pages_fetched = 0
        nodes_captured = 0
        item_start_time = time.monotonic()

        log.info(
            "worker_processing_item_start",
            worker_id=self.worker_id,
            repository=item.repository,
            page=page_number,
            cursor=cursor,
        )

        while True:
            try:
                active_client = self._get_or_create_client(org=owner)
                async for page in active_client.iter_pull_request_pages(
                    owner,
                    name,
                    self.start_at,
                    self.end_at,
                    start_cursor=cursor,
                ):
                    relevant = [node for node in page.nodes if self._in_window(node)]
                    self.raw_store.append_page(
                        ingestion_run_id=item.run_id,
                        owner=owner,
                        name=name,
                        page_number=page_number,
                        cursor=cursor,
                        repository_id=page.repository_id,
                        repository_name_with_owner=page.repository_name_with_owner,
                        nodes=relevant,
                    )
                    pages_fetched += 1
                    nodes_captured += len(relevant)
                    INGESTION_PAGES_TOTAL.inc(1.0, repository=item.repository, run_id=item.run_id)
                    INGESTION_NODES_TOTAL.inc(
                        float(len(relevant)), repository=item.repository, run_id=item.run_id
                    )
                    next_page = page_number + 1
                    self.checkpoint_store.save(
                        item.run_id,
                        item.repository,
                        {
                            "repository": item.repository,
                            "next_page": next_page,
                            "cursor": page.end_cursor,
                        },
                    )
                    page_number = next_page
                    cursor = page.end_cursor

                    if self.shutdown_requested:
                        log.info(
                            "worker_shutdown_after_page_checkpoint",
                            worker_id=self.worker_id,
                            repository=item.repository,
                            page_number=page_number,
                        )
                        return {
                            "repository": item.repository,
                            "pages": pages_fetched,
                            "nodes": nodes_captured,
                            "completed": False,
                        }

                # Successfully finished all available pages
                break

            except RateLimitError as exc:
                log.warning(
                    "worker_rate_limited",
                    worker_id=self.worker_id,
                    repository=item.repository,
                    error=str(exc),
                )
                if self._can_rotate_token(org=owner):
                    self._rotate_token(org=owner)
                    continue
                raise

        item_duration = time.monotonic() - item_start_time
        INGESTION_DURATION_SECONDS.observe(item_duration, repository=item.repository)

        log.info(
            "worker_processing_item_complete",
            worker_id=self.worker_id,
            repository=item.repository,
            pages_fetched=pages_fetched,
            nodes_captured=nodes_captured,
            duration_seconds=round(item_duration, 3),
        )
        return {
            "repository": item.repository,
            "pages": pages_fetched,
            "nodes": nodes_captured,
            "completed": True,
        }

    async def run(self, queue: WorkQueue) -> dict[str, Any]:
        """Run worker loop, draining items from queue until empty or shutdown."""
        loop = asyncio.get_running_loop()
        signals = (signal.SIGTERM, signal.SIGINT)

        def _sig_handler() -> None:
            log.info("worker_signal_received", worker_id=self.worker_id)
            self.request_shutdown()

        for sig in signals:
            with contextlib.suppress(NotImplementedError, RuntimeError, ValueError):
                loop.add_signal_handler(sig, _sig_handler)

        repos_processed = 0
        pages_total = 0
        nodes_total = 0

        try:
            while not self.shutdown_requested:
                item = await queue.dequeue()
                if item is None:
                    break
                try:
                    res = await self.process_item(item)
                    pages_total += int(res.get("pages", 0))
                    nodes_total += int(res.get("nodes", 0))
                    if res.get("completed", False):
                        repos_processed += 1
                        await queue.mark_done(item)
                    else:
                        log.info(
                            "worker_interrupted_by_shutdown",
                            worker_id=self.worker_id,
                            repo=item.repository,
                        )
                        break
                except Exception as exc:
                    log.error(
                        "worker_item_failure",
                        worker_id=self.worker_id,
                        repo=item.repository,
                        error=str(exc),
                    )
                    await queue.mark_failed(item, str(exc))
                    if self.shutdown_requested:
                        break
        finally:
            for sig in signals:
                with contextlib.suppress(NotImplementedError, RuntimeError, ValueError):
                    loop.remove_signal_handler(sig)
            if self._client is not None and not self._client.is_closed and self._owns_client:
                await self._client.close()

        return {
            "worker_id": self.worker_id,
            "repositories_processed": repos_processed,
            "pages_fetched": pages_total,
            "nodes_captured": nodes_total,
            "shutdown_requested": self.shutdown_requested,
        }
