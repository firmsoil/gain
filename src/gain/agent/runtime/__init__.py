"""Runtime.next package: SLA slack budgeting and tiered edge-cloud execution."""

from gain.agent.runtime.router import ModelTier, TaskCriticality, TieredModelRouter
from gain.agent.runtime.slack import SLABudgetTracker, TaskSlackAllocation

__all__ = [
    "SLABudgetTracker",
    "TaskSlackAllocation",
    "TieredModelRouter",
    "ModelTier",
    "TaskCriticality",
]
