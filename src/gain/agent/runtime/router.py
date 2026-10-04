"""Tiered Model Router for Edge-Cloud compound application execution (Runtime.next).

Directs analytical queries to local SLM edge runners or cloud frontier models
guided by task complexity and SLA slack budgets (Hassan et al. 2026).
"""

from __future__ import annotations

from enum import StrEnum

import structlog

log = structlog.get_logger(__name__)


class ModelTier(StrEnum):
    """Execution tiers for FMware model invocation."""

    LOCAL_EDGE = "local_edge"
    CLOUD_FRONTIER = "cloud_frontier"
    DETERMINISTIC_CACHE = "deterministic_cache"


class TaskCriticality(StrEnum):
    """Complexity classification of analytical synthesis requests."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TieredModelRouter:
    """Intelligent SLA-aware router balancing latency, cost, and analytical depth."""

    def __init__(
        self,
        edge_available: bool = True,
        frontier_available: bool = True,
        min_frontier_slack_ms: float = 1500.0,
    ) -> None:
        self.edge_available = edge_available
        self.frontier_available = frontier_available
        self.min_frontier_slack_ms = min_frontier_slack_ms

    def select_tier(
        self,
        criticality: TaskCriticality,
        remaining_slack_ms: float,
    ) -> tuple[ModelTier, str]:
        """Select execution tier based on task complexity and remaining slack buffer."""
        # 1. Critical slack floor: fall back to zero-token deterministic provider
        if remaining_slack_ms < 500.0:
            reason = (
                f"Slack buffer critical ({remaining_slack_ms:.1f}ms < 500.0ms); "
                "fallback to zero-token deterministic engine to prevent SLA breach."
            )
            log.warning("router_sla_fallback_deterministic", remaining_slack_ms=remaining_slack_ms)
            return ModelTier.DETERMINISTIC_CACHE, reason

        # 2. Low-complexity tasks: route to local edge SLM to minimize latency and token cost
        if criticality == TaskCriticality.LOW:
            if self.edge_available:
                return (
                    ModelTier.LOCAL_EDGE,
                    (
                        "Low-complexity task routed to local edge SLM "
                        "(zero token cost, <200ms latency)."
                    ),
                )
            return (
                ModelTier.DETERMINISTIC_CACHE,
                "Local edge runner unavailable; routed to deterministic cache.",
            )

        # 3. Medium-complexity tasks: route to edge if tight slack, otherwise cloud frontier
        if criticality == TaskCriticality.MEDIUM:
            if remaining_slack_ms < self.min_frontier_slack_ms:
                if self.edge_available:
                    return (
                        ModelTier.LOCAL_EDGE,
                        (
                            f"Tight slack ({remaining_slack_ms:.1f}ms); "
                            "routed to local edge SLM to protect SLA."
                        ),
                    )
                return (
                    ModelTier.DETERMINISTIC_CACHE,
                    "Tight slack and edge unavailable; fallback to deterministic cache.",
                )
            if self.frontier_available:
                return (
                    ModelTier.CLOUD_FRONTIER,
                    "Medium-complexity task with ample slack routed to cloud frontier model.",
                )
            return (
                ModelTier.LOCAL_EDGE if self.edge_available else ModelTier.DETERMINISTIC_CACHE,
                "Cloud frontier unavailable; fallback to edge/deterministic tier.",
            )

        # 4. High-complexity tasks (causal reasoning): prefer cloud frontier if slack permits
        if criticality == TaskCriticality.HIGH:
            if remaining_slack_ms >= self.min_frontier_slack_ms and self.frontier_available:
                return (
                    ModelTier.CLOUD_FRONTIER,
                    (
                        f"High-complexity causal investigation with {remaining_slack_ms:.1f}ms "
                        "slack routed to frontier model."
                    ),
                )
            if self.edge_available:
                log.info(
                    "router_frontier_slack_insufficient_edge_fallback",
                    remaining_slack_ms=remaining_slack_ms,
                    min_required=self.min_frontier_slack_ms,
                )
                return (
                    ModelTier.LOCAL_EDGE,
                    (
                        f"High-complexity task with constrained slack "
                        f"({remaining_slack_ms:.1f}ms); routed to edge SLM."
                    ),
                )
            return (
                ModelTier.DETERMINISTIC_CACHE,
                (
                    "Frontier slack insufficient and edge unavailable; "
                    "fallback to deterministic engine."
                ),
            )

        return ModelTier.DETERMINISTIC_CACHE, "Default deterministic route."
