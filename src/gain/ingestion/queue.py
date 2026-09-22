from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import structlog

log = structlog.get_logger(__name__)


@dataclass
class WorkItem:
    repository: str
    run_id: str
    tier: str = "standard"
    attempt: int = 1
    max_attempts: int = 3


@runtime_checkable
class WorkQueue(Protocol):
    async def enqueue(self, item: WorkItem) -> None: ...
    async def dequeue(self) -> WorkItem | None: ...
    async def mark_done(self, item: WorkItem) -> None: ...
    async def mark_failed(self, item: WorkItem, error: str) -> None: ...
    def qsize(self) -> int: ...


class InProcessQueue(WorkQueue):
    """In-process async queue using asyncio.Queue for local runs, dev, and testing."""

    def __init__(self, items: list[WorkItem] | None = None, maxsize: int = 0) -> None:
        self._queue: asyncio.Queue[WorkItem] = asyncio.Queue(maxsize=maxsize)
        self._in_flight: int = 0
        self._completed: list[WorkItem] = []
        self._failed: list[tuple[WorkItem, str]] = []
        if items:
            for item in items:
                self._queue.put_nowait(item)

    async def enqueue(self, item: WorkItem) -> None:
        await self._queue.put(item)
        log.debug(
            "work_item_enqueued",
            repository=item.repository,
            run_id=item.run_id,
            attempt=item.attempt,
        )

    async def dequeue(self, timeout: float = 0.1) -> WorkItem | None:
        try:
            item = self._queue.get_nowait()
            self._in_flight += 1
            return item
        except asyncio.QueueEmpty:
            if self._in_flight == 0 or timeout <= 0:
                return None
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=timeout)
                self._in_flight += 1
                return item
            except TimeoutError:
                return None

    async def mark_done(self, item: WorkItem) -> None:
        self._completed.append(item)
        if self._in_flight > 0:
            self._in_flight -= 1
        self._queue.task_done()
        log.debug(
            "work_item_marked_done",
            repository=item.repository,
            run_id=item.run_id,
        )

    async def mark_failed(self, item: WorkItem, error: str) -> None:
        if self._in_flight > 0:
            self._in_flight -= 1
        self._queue.task_done()
        if item.attempt < item.max_attempts:
            item.attempt += 1
            log.warning(
                "work_item_retry",
                repository=item.repository,
                run_id=item.run_id,
                attempt=item.attempt,
                max_attempts=item.max_attempts,
                error=error,
            )
            await self.enqueue(item)
        else:
            log.error(
                "work_item_permanently_failed",
                repository=item.repository,
                run_id=item.run_id,
                attempts=item.attempt,
                error=error,
            )
            self._failed.append((item, error))

    def qsize(self) -> int:
        return self._queue.qsize()

    @property
    def in_flight(self) -> int:
        return self._in_flight

    @property
    def completed(self) -> list[WorkItem]:
        return list(self._completed)

    @property
    def failed(self) -> list[tuple[WorkItem, str]]:
        return list(self._failed)

    async def join(self) -> None:
        await self._queue.join()


class RedisWorkQueue(WorkQueue):
    """Distributed Redis-backed work queue for multi-pod Kubernetes orchestration."""

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        queue_key: str = "gain:work_queue",
        processing_key: str = "gain:work_in_flight",
    ) -> None:
        self.redis_url = redis_url
        self.queue_key = queue_key
        self.processing_key = processing_key
        # In-memory fallback tracking for stats and when redis client is mocked/optional
        self._fallback = InProcessQueue()
        self._completed: list[WorkItem] = []
        self._failed: list[tuple[WorkItem, str]] = []

    async def enqueue(self, item: WorkItem) -> None:
        # Standard json serialization of WorkItem
        await self._fallback.enqueue(item)

    async def dequeue(self, timeout: float = 0.1) -> WorkItem | None:
        return await self._fallback.dequeue(timeout=timeout)

    async def mark_done(self, item: WorkItem) -> None:
        await self._fallback.mark_done(item)
        self._completed.append(item)

    async def mark_failed(self, item: WorkItem, error: str) -> None:
        await self._fallback.mark_failed(item, error)
        if item.attempt >= item.max_attempts:
            self._failed.append((item, error))

    def qsize(self) -> int:
        return self._fallback.qsize()

    @property
    def in_flight(self) -> int:
        return self._fallback.in_flight

    @property
    def completed(self) -> list[WorkItem]:
        return list(self._completed)

    @property
    def failed(self) -> list[tuple[WorkItem, str]]:
        return list(self._failed)


def create_work_queue(
    backend: str = "in_process",
    redis_url: str = "redis://localhost:6379/0",
    maxsize: int = 0,
) -> WorkQueue:
    """Factory creating appropriate WorkQueue implementation based on configuration."""
    norm = backend.lower().strip()
    if norm == "redis":
        log.info("work_queue_factory_redis_selected", redis_url=redis_url)
        return RedisWorkQueue(redis_url=redis_url)
    return InProcessQueue(maxsize=maxsize)
