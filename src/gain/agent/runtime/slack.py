"""SLA Slack Budgeting Engine for compound FMware execution (Runtime.next).

Implements per-task slack decomposition and dynamic time buffering for
directed acyclic graph investigations (Hassan et al. 2026).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import structlog

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class TaskSlackAllocation:
    """Record of slack allocated, consumed, and saved for an individual task."""

    step_id: str
    allocated_slack_ms: float
    actual_duration_ms: float
    saved_slack_ms: float
    completed_at_monotonic: float


class SLABudgetTracker:
    """Tracks end-to-end SLA and dynamically manages per-step slack buffers.

    As steps finish ahead of schedule, saved slack is pooled and reallocated
    to downstream tasks (e.g. LLM reasoning and evidence synthesis).
    """

    def __init__(
        self,
        total_budget_ms: float = 10000.0,
        sla_target_name: str = "interactive_investigation",
    ) -> None:
        self.total_budget_ms = total_budget_ms
        self.sla_target_name = sla_target_name
        self.start_time = time.monotonic()
        self.allocations: list[TaskSlackAllocation] = []

    @property
    def elapsed_ms(self) -> float:
        """Total elapsed wall-clock time in milliseconds since tracker instantiation."""
        return (time.monotonic() - self.start_time) * 1000.0

    @property
    def remaining_slack_ms(self) -> float:
        """Remaining slack buffer in milliseconds until total SLA budget exhaustion."""
        return max(0.0, self.total_budget_ms - self.elapsed_ms)

    @property
    def is_slack_exhausted(self) -> bool:
        """Return True if remaining slack has dropped below safety floor (100ms)."""
        return self.remaining_slack_ms <= 100.0

    def allocate_step_slack(
        self,
        step_id: str,
        steps_remaining: int,
        weight: float = 1.0,
    ) -> float:
        """Decompose remaining slack for the upcoming execution step."""
        if steps_remaining <= 0:
            return self.remaining_slack_ms
        base_share = self.remaining_slack_ms / float(steps_remaining)
        allocated = max(50.0, base_share * weight)
        log.debug(
            "sla_slack_allocated",
            step_id=step_id,
            allocated_ms=round(allocated, 2),
            remaining_slack_ms=round(self.remaining_slack_ms, 2),
        )
        return allocated

    def record_step_completion(
        self,
        step_id: str,
        allocated_slack_ms: float,
        actual_duration_ms: float,
    ) -> TaskSlackAllocation:
        """Record task duration and update accumulated slack surplus/deficit."""
        saved = allocated_slack_ms - actual_duration_ms
        allocation = TaskSlackAllocation(
            step_id=step_id,
            allocated_slack_ms=allocated_slack_ms,
            actual_duration_ms=actual_duration_ms,
            saved_slack_ms=saved,
            completed_at_monotonic=time.monotonic(),
        )
        self.allocations.append(allocation)
        log.debug(
            "sla_step_completed",
            step_id=step_id,
            duration_ms=round(actual_duration_ms, 2),
            saved_slack_ms=round(saved, 2),
            remaining_slack_ms=round(self.remaining_slack_ms, 2),
        )
        return allocation

    def to_audit_record(self) -> dict[str, Any]:
        """Export structured audit metadata for observability and post-run profiling."""
        total_saved = sum(a.saved_slack_ms for a in self.allocations)
        return {
            "sla_target": self.sla_target_name,
            "total_budget_ms": self.total_budget_ms,
            "elapsed_ms": round(self.elapsed_ms, 2),
            "remaining_slack_ms": round(self.remaining_slack_ms, 2),
            "total_saved_slack_ms": round(total_saved, 2),
            "is_exhausted": self.is_slack_exhausted,
            "step_count": len(self.allocations),
            "step_allocations": [
                {
                    "step_id": a.step_id,
                    "allocated_ms": round(a.allocated_slack_ms, 2),
                    "actual_ms": round(a.actual_duration_ms, 2),
                    "saved_ms": round(a.saved_slack_ms, 2),
                }
                for a in self.allocations
            ],
        }
