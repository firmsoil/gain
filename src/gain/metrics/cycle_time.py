from __future__ import annotations

from dataclasses import dataclass
from statistics import mean

from gain.model.pr import PullRequest


@dataclass(frozen=True)
class CycleTimeObservation:
    metric_id: str
    metric_version: int
    github_node_id: str
    repository_name_with_owner: str
    pr_number: int
    cycle_time_seconds: float


class CycleTimeMetric:
    metric_id = "GAIN-PR-001"
    metric_version = 1

    @classmethod
    def observations(cls, prs: list[PullRequest]) -> list[CycleTimeObservation]:
        output: list[CycleTimeObservation] = []
        for pr in prs:
            seconds = pr.cycle_time_seconds()
            if seconds is None:
                continue
            if seconds < 0:
                continue
            output.append(
                CycleTimeObservation(
                    metric_id=cls.metric_id,
                    metric_version=cls.metric_version,
                    github_node_id=pr.github_node_id,
                    repository_name_with_owner=pr.repository_name_with_owner,
                    pr_number=pr.number,
                    cycle_time_seconds=seconds,
                )
            )
        return output

    @classmethod
    def summary(
        cls,
        observations: list[CycleTimeObservation],
        total_prs: int | None = None,
    ) -> dict[str, float | int | None]:
        values = sorted(item.cycle_time_seconds for item in observations)
        merged_count = len(values)
        return {
            "count": merged_count,
            "merged_count": merged_count,
            "total_evaluated": total_prs if total_prs is not None else merged_count,
            "p50_seconds": _percentile(values, 0.50),
            "p75_seconds": _percentile(values, 0.75),
            "p90_seconds": _percentile(values, 0.90),
            "p95_seconds": _percentile(values, 0.95),
            "mean_seconds": mean(values) if values else None,
        }


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    rank = q * (len(values) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(values) - 1)
    fraction = rank - lower
    return values[lower] + fraction * (values[upper] - values[lower])
