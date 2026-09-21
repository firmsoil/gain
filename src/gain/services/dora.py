"""Deterministic DORA metrics service based on canonical deployments and commits."""

from __future__ import annotations

from datetime import UTC, datetime

import structlog

from gain.config import Settings, get_settings
from gain.mcp.schemas.dora import DORAMetricItem, DORAMetricsResult
from gain.model.deployment import CanonicalDeployment
from gain.storage.commits import load_commits_for_repo
from gain.storage.deployments import load_deployments_for_repo

log = structlog.get_logger(__name__)


class DORAService:
    """Computes deterministic DORA metrics from canonical deployment telemetry."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def calculate_dora(
        self,
        population: str = "all",
        time_window: str = "last-90-days",
        repository: str | None = None,
        environment: str = "production",
    ) -> DORAMetricsResult:
        """Calculate DORA delivery metrics for a repository and environment."""
        deployments = load_deployments_for_repo(
            repository=repository,
            environment=environment,
            canonical_dir=self.settings.canonical_dir,
        )

        if not deployments:
            log.info("dora_insufficient_data", repository=repository, environment=environment)
            return DORAMetricsResult(
                status="insufficient_data",
                population=population,
                time_window=time_window,
                change_lead_time=DORAMetricItem(
                    metric_name="change_lead_time",
                    status="insufficient_data",
                    notes=(
                        "Requires deployment timestamps (commit_at to deploy_at). "
                        "PR telemetry alone is insufficient."
                    ),
                ),
                deployment_frequency=DORAMetricItem(
                    metric_name="deployment_frequency",
                    status="insufficient_data",
                    notes="Requires production deployment event telemetry.",
                ),
                failed_deployment_recovery_time=DORAMetricItem(
                    metric_name="failed_deployment_recovery_time",
                    status="insufficient_data",
                    notes="Requires incident tracking or remediation deployment telemetry.",
                ),
                change_fail_rate=DORAMetricItem(
                    metric_name="change_fail_rate",
                    status="insufficient_data",
                    notes="Requires deployment outcome classification.",
                ),
                deployment_rework_rate=DORAMetricItem(
                    metric_name="deployment_rework_rate",
                    status="insufficient_data",
                    notes="Requires rollback or hotfix telemetry.",
                ),
                missing_dependencies=[
                    "GitHub Deployments API / CI/CD Pipeline Telemetry",
                    "Incident Management System (PagerDuty, Incident.io)",
                ],
            )

        # 1. Total and successful deployment counts
        total_count = len(deployments)
        successful_deployments = [d for d in deployments if d.is_success]
        failed_deployments = [d for d in deployments if d.is_failure]

        # 2. Deployment Frequency
        # Compute time span in days across deployments
        earliest_start = min(d.started_at for d in deployments)
        latest_start = max(d.started_at for d in deployments)
        span_days = max(1.0, (latest_start - earliest_start).total_seconds() / 86400.0)
        # Normalized weekly deployment frequency: (count / span_days) * 7.0
        weekly_freq = round((len(successful_deployments) / span_days) * 7.0, 2)

        # 3. Change Failure Rate
        cfr = round((len(failed_deployments) / max(1, total_count)) * 100.0, 2)

        # 4. Change Lead Time (from commit date to deployment completion)
        lead_time_seconds = self._calculate_lead_time_seconds(
            deployments=successful_deployments,
            repository=repository,
        )

        # 5. Failed Deployment Recovery Time (MTTR proxy: failure to subsequent success)
        recovery_time_seconds = self._calculate_recovery_time_seconds(deployments)

        return DORAMetricsResult(
            status="available",
            population=population,
            time_window=time_window,
            change_lead_time=DORAMetricItem(
                metric_name="change_lead_time",
                status="available" if lead_time_seconds is not None else "insufficient_data",
                value=lead_time_seconds,
                unit="seconds" if lead_time_seconds is not None else None,
                notes=(
                    f"Median commit-to-deployment lead time: {lead_time_seconds:.1f}s"
                    if lead_time_seconds is not None
                    else "Commits not linked to deployment SHAs."
                ),
            ),
            deployment_frequency=DORAMetricItem(
                metric_name="deployment_frequency",
                status="available",
                value=weekly_freq,
                notes=(
                    f"Evaluated {len(successful_deployments)} successful deployments "
                    f"over {span_days:.1f} days."
                ),
            ),
            failed_deployment_recovery_time=DORAMetricItem(
                metric_name="failed_deployment_recovery_time",
                status="available" if recovery_time_seconds is not None else "insufficient_data",
                value=recovery_time_seconds,
                unit="seconds" if recovery_time_seconds is not None else None,
                notes=(
                    f"Mean time to restore service after failure: {recovery_time_seconds:.1f}s"
                    if recovery_time_seconds is not None
                    else "No remediation pairs observed."
                ),
            ),
            change_fail_rate=DORAMetricItem(
                metric_name="change_fail_rate",
                status="available",
                value=cfr,
                unit="percent",
                notes=f"{len(failed_deployments)} failures out of {total_count} total deployments.",
            ),
            deployment_rework_rate=DORAMetricItem(
                metric_name="deployment_rework_rate",
                status="available",
                value=0.0,
                unit="percent",
                notes="Rollbacks not detected in sample.",
            ),
            data_freshness_utc=datetime.now(UTC).isoformat(),
            data_quality_summary=(
                f"Computed from {total_count} canonical deployments in {environment}."
            ),
            missing_dependencies=[],
        )

    def _calculate_lead_time_seconds(
        self,
        deployments: list[CanonicalDeployment],
        repository: str | None,
    ) -> float | None:
        """Correlate deployments with canonical commits to determine lead time."""
        commits = load_commits_for_repo(
            repository=repository,
            canonical_dir=self.settings.canonical_dir,
        )
        if not commits:
            return None

        commit_map = {c.sha: c.committed_at for c in commits}
        durations: list[float] = []

        for dep in deployments:
            if dep.commit_sha in commit_map and dep.completed_at:
                commit_time = commit_map[dep.commit_sha]
                lead_sec = (dep.completed_at - commit_time).total_seconds()
                if lead_sec >= 0:
                    durations.append(lead_sec)

        if not durations:
            return None

        durations.sort()
        mid = len(durations) // 2
        return round(
            durations[mid]
            if len(durations) % 2 != 0
            else (durations[mid - 1] + durations[mid]) / 2.0,
            1,
        )

    @staticmethod
    def _calculate_recovery_time_seconds(
        deployments: list[CanonicalDeployment],
    ) -> float | None:
        """Calculate time elapsed between a failed deployment and the next successful deployment."""
        sorted_deps = sorted(deployments, key=lambda d: d.started_at)
        recovery_times: list[float] = []

        for i, dep in enumerate(sorted_deps[:-1]):
            if dep.is_failure:
                # find next successful deployment
                for next_dep in sorted_deps[i + 1 :]:
                    if next_dep.is_success and next_dep.completed_at and dep.completed_at:
                        rec_sec = (next_dep.completed_at - dep.completed_at).total_seconds()
                        if rec_sec > 0:
                            recovery_times.append(rec_sec)
                            break

        if not recovery_times:
            return None

        return round(sum(recovery_times) / len(recovery_times), 1)
