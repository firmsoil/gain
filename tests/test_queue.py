from __future__ import annotations

import pytest

from gain.config import Settings
from gain.ingestion.queue import (
    InProcessQueue,
    RedisWorkQueue,
    WorkItem,
    WorkQueue,
    create_work_queue,
)


@pytest.mark.anyio
async def test_in_process_queue_lifecycle() -> None:
    queue = InProcessQueue(maxsize=10)
    assert isinstance(queue, WorkQueue)
    assert queue.qsize() == 0

    item = WorkItem(repository="octocat/Hello-World", run_id="run-1", tier="critical")
    await queue.enqueue(item)
    assert queue.qsize() == 1

    dequeued = await queue.dequeue(timeout=0.1)
    assert dequeued is not None
    assert dequeued.repository == "octocat/Hello-World"
    assert dequeued.tier == "critical"
    assert queue.in_flight == 1

    await queue.mark_done(dequeued)
    assert queue.in_flight == 0
    assert len(queue.completed) == 1


@pytest.mark.anyio
async def test_in_process_queue_retry_and_permanent_fail() -> None:
    queue = InProcessQueue()
    item = WorkItem(repository="octocat/retry-repo", run_id="run-2", attempt=1, max_attempts=2)
    await queue.enqueue(item)

    # First attempt: marks failed and re-enqueues
    d1 = await queue.dequeue(timeout=0.1)
    assert d1 is not None
    await queue.mark_failed(d1, "Network timeout")
    assert queue.qsize() == 1
    assert len(queue.failed) == 0

    # Second attempt: permanently fails
    d2 = await queue.dequeue(timeout=0.1)
    assert d2 is not None
    assert d2.attempt == 2
    await queue.mark_failed(d2, "Persistent failure")
    assert queue.qsize() == 0
    assert len(queue.failed) == 1
    failed_item, reason = queue.failed[0]
    assert failed_item.repository == "octocat/retry-repo"
    assert "Persistent failure" in reason


@pytest.mark.anyio
async def test_redis_work_queue_protocol_and_operations() -> None:
    redis_queue = RedisWorkQueue(redis_url="redis://localhost:6379/1")
    assert isinstance(redis_queue, WorkQueue)
    assert redis_queue.qsize() == 0

    item = WorkItem(repository="firmsoil/service-alpha", run_id="run-scale", tier="core")
    await redis_queue.enqueue(item)
    assert redis_queue.qsize() == 1

    dequeued = await redis_queue.dequeue(timeout=0.1)
    assert dequeued is not None
    assert dequeued.repository == "firmsoil/service-alpha"

    await redis_queue.mark_done(dequeued)
    assert len(redis_queue.completed) == 1


def test_create_work_queue_factory() -> None:
    q_default = create_work_queue(backend="in_process", maxsize=50)
    assert isinstance(q_default, InProcessQueue)

    q_redis = create_work_queue(backend="redis", redis_url="redis://custom:6379/0")
    assert isinstance(q_redis, RedisWorkQueue)
    assert q_redis.redis_url == "redis://custom:6379/0"

    settings = Settings(queue_backend="redis", redis_url="redis://cluster:6379/2")
    q_settings = create_work_queue(backend=settings.queue_backend, redis_url=settings.redis_url)
    assert isinstance(q_settings, RedisWorkQueue)
