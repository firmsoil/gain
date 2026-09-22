from __future__ import annotations

import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import structlog

log = structlog.get_logger(__name__)


class Span:
    def __init__(self, name: str, trace_id: str, parent_id: str | None = None) -> None:
        self.name = name
        self.trace_id = trace_id
        self.span_id = str(uuid.uuid4())[:8]
        self.parent_id = parent_id
        self.start_time = time.monotonic()
        self.end_time: float | None = None
        self.attributes: dict[str, Any] = {}
        self.status: str = "ok"

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def set_error(self, exc: BaseException) -> None:
        self.status = "error"
        self.attributes["error.type"] = exc.__class__.__name__
        self.attributes["error.message"] = str(exc)

    def finish(self) -> None:
        self.end_time = time.monotonic()
        duration_ms = (self.end_time - self.start_time) * 1000.0
        log.debug(
            "trace_span_completed",
            name=self.name,
            trace_id=self.trace_id,
            span_id=self.span_id,
            duration_ms=round(duration_ms, 2),
            status=self.status,
            **self.attributes,
        )


@contextmanager
def trace_span(
    name: str,
    trace_id: str | None = None,
    parent_id: str | None = None,
    **attributes: Any,
) -> Iterator[Span]:
    active_trace_id = trace_id or str(uuid.uuid4())
    span = Span(name=name, trace_id=active_trace_id, parent_id=parent_id)
    for k, v in attributes.items():
        span.set_attribute(k, v)
    try:
        yield span
    except BaseException as exc:
        span.set_error(exc)
        raise
    finally:
        span.finish()
