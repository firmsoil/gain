from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer

from gain.config import get_settings
from gain.logging import configure_logging
from gain.metrics.catalog import MetricCatalog
from gain.metrics.cycle_time import CycleTimeMetric
from gain.metrics.monthly_stats import MonthlyStatsMetric
from gain.storage.analytics import (
    read_canonical,
    write_cycle_time_observations,
    write_monthly_stats,
)


def register_metrics_commands(app: typer.Typer) -> None:
    @app.command()
    def compute(
        canonical_path: Path = typer.Option(..., exists=True, dir_okay=False, readable=True),
        metric_catalog: Path = typer.Option(Path("docs/metrics/metric-catalog.yaml"), exists=True),
    ) -> None:
        """Compute the initial GAIN cycle-time metric from canonical PR data."""
        configure_logging()
        settings = get_settings()
        settings.ensure_directories()
        catalog = MetricCatalog(metric_catalog)
        definition = catalog.get(CycleTimeMetric.metric_id)
        if int(definition["metric_version"]) != CycleTimeMetric.metric_version:
            raise typer.BadParameter(
                "Code and Metric Catalog versions do not match for GAIN-PR-001"
            )
        prs = read_canonical(canonical_path)
        observations = CycleTimeMetric.observations(prs)
        output_path = settings.metrics_dir / "gain-pr-001-cycle-time.parquet"
        write_cycle_time_observations(observations, output_path)
        summary_data: dict[str, Any] = dict(CycleTimeMetric.summary(observations))
        summary_data["metric_id"] = CycleTimeMetric.metric_id
        summary_data["metric_version"] = CycleTimeMetric.metric_version
        summary_data["generated_at"] = datetime.now(UTC).isoformat()
        summary_path = settings.metrics_dir / "gain-pr-001-cycle-time-summary.json"
        summary_path.write_text(
            json.dumps(summary_data, indent=2, sort_keys=True, default=str), encoding="utf-8"
        )
        typer.echo(json.dumps(summary_data, indent=2, sort_keys=True, default=str))

    @app.command("monthly-stats")
    def monthly_stats(
        canonical_path: Path = typer.Option(
            ..., exists=True, dir_okay=False, readable=True, help="Canonical PR parquet file."
        ),
        months: int = typer.Option(12, help="Number of trailing months to analyze."),
        by_repo: bool = typer.Option(False, help="Segment monthly statistics by repository."),
        by_author: bool = typer.Option(False, help="Segment monthly statistics by PR author."),
        include_bots: bool = typer.Option(True, help="Include bot accounts in statistics."),
        output_format: str = typer.Option("table", help="Output format: table, json, or parquet."),
        metric_catalog: Path = typer.Option(Path("docs/metrics/metric-catalog.yaml"), exists=True),
    ) -> None:
        """Compute monthly tabular statistics on PRs created, merged, and closed."""
        configure_logging()
        settings = get_settings()
        settings.ensure_directories()
        catalog = MetricCatalog(metric_catalog)
        definition = catalog.get(MonthlyStatsMetric.metric_id)
        if int(definition["metric_version"]) != MonthlyStatsMetric.metric_version:
            raise typer.BadParameter(
                f"Code and Metric Catalog versions do not match for {MonthlyStatsMetric.metric_id}"
            )
        prs = read_canonical(canonical_path)
        stats = MonthlyStatsMetric.calculate(
            prs,
            months=months,
            by_repo=by_repo,
            by_author=by_author,
            include_bots=include_bots,
        )

        parquet_path = settings.metrics_dir / "gain-pr-010-monthly-stats.parquet"
        write_monthly_stats(stats, parquet_path)

        summary_data = {
            "metric_id": MonthlyStatsMetric.metric_id,
            "metric_version": MonthlyStatsMetric.metric_version,
            "generated_at": datetime.now(UTC).isoformat(),
            "months_analyzed": months,
            "by_repo": by_repo,
            "by_author": by_author,
            "include_bots": include_bots,
            "monthly_records": [s.to_dict() for s in stats],
        }
        json_path = settings.metrics_dir / "gain-pr-010-monthly-stats.json"
        json_path.write_text(json.dumps(summary_data, indent=2, default=str), encoding="utf-8")

        if output_format == "json":
            typer.echo(json.dumps(summary_data, indent=2, default=str))
        elif output_format == "parquet":
            typer.echo(f"Parquet written to: {parquet_path}")
        else:
            typer.echo(MonthlyStatsMetric.format_table(stats))

    @app.command("ai-impact")
    def cli_ai_impact(
        repo: str = typer.Option(
            "firmsoil/gain", "--repo", "-r", help="Target repository name with owner."
        ),
        json_output: bool = typer.Option(False, "--json", help="Output raw JSON payload."),
    ) -> None:
        """Evaluate AI developer tooling impact across delivery flow cohorts."""
        from gain.services.ai_impact import AIImpactService

        configure_logging()
        svc = AIImpactService()
        res = svc.analyze_impact(repository=repo)
        if json_output:
            typer.echo(json.dumps(res.model_dump(mode="json"), indent=2))
        else:
            typer.echo(f"AI Impact Status: {res.status} ({res.classification})")
            for f in res.findings:
                typer.echo(f"- {f}")
            for lim in res.limitations:
                typer.echo(f"  * Limitation: {lim}")

    @app.command("ai-roi")
    def cli_ai_roi(
        population: str = typer.Option(
            "firmsoil/gain", "--population", "-p", help="Target population/repository."
        ),
        devs: int = typer.Option(25, "--devs", "-d", help="Number of active developers."),
        hourly_rate: float = typer.Option(
            85.0, "--hourly-rate", help="Developer hourly cost rate ($/hr)."
        ),
        seat_cost: float = typer.Option(
            19.0, "--seat-cost", help="Monthly license cost per seat ($/mo)."
        ),
        dora_model: bool = typer.Option(
            False, "--dora", help="Use Google Cloud DORA 2026 two-ledger economic framework."
        ),
        staff_size: int | None = typer.Option(
            None, "--staff-size", help="Technical staff size in FTEs (DORA model)."
        ),
        salary: float = typer.Option(
            176000.0, "--salary", help="Fully-loaded developer salary (DORA model)."
        ),
        training_cost: float = typer.Option(
            9600.0, "--training-cost", help="Training and enablement cost per user (DORA model)."
        ),
        infra_cost: float = typer.Option(
            100000.0, "--infra-cost", help="Annual AI infrastructure cost (DORA model)."
        ),
        j_curve_drop: float = typer.Option(
            0.15, "--j-curve-drop", help="J-Curve adoption productivity drop (DORA model)."
        ),
        j_curve_months: float = typer.Option(
            3.0, "--j-curve-months", help="J-Curve learning phase in months (DORA model)."
        ),
        json_output: bool = typer.Option(False, "--json", help="Output raw JSON scenario payload."),
    ) -> None:
        """Calculate deterministic AI tooling economic ROI and sensitivity scenarios."""
        from gain.services.ai_roi import AIROIService

        configure_logging()
        svc = AIROIService()

        if dora_model or staff_size is not None:
            res = svc.calculate_roi_scenario(
                population=population,
                staff_size=staff_size or 500,
                salary=salary,
                annual_training_cost_per_user=training_cost,
                annual_infra_cost=infra_cost,
                j_curve_drop=j_curve_drop,
                j_curve_months=j_curve_months,
                use_dora_model=True,
            )
        else:
            res = svc.calculate_roi_scenario(
                population=population,
                developer_count=devs,
                hourly_rate=hourly_rate,
                monthly_license_cost=seat_cost,
            )

        if json_output:
            typer.echo(json.dumps(res.model_dump(mode="json"), indent=2))
        else:
            typer.echo(f"Modeled AI Tooling ROI: {res.roi_percentage:.1f}%")
            if res.model_version.startswith("gain-dora-roi"):
                typer.echo(f"Total First-Year Investment: ${res.investment_cost:,.2f}")
                typer.echo(f"  - Direct Hard Costs:       ${res.hard_costs:,.2f}")
                typer.echo(f"  - J-Curve Tuition Cost:    ${res.j_curve_cost:,.2f}")
                typer.echo(f"Total Annual Gross Value:    ${res.total_annual_value:,.2f}")
                typer.echo(f"  - Headcount Reinvestment:  ${res.headcount_reinvestment_value:,.2f}")
                typer.echo(f"  - Feature Revenue Lift:    ${res.feature_revenue_lift:,.2f}")
                typer.echo(f"  - Downtime Stability Tax:  ${res.instability_impact:,.2f}")
                typer.echo(f"Net Economic Benefit:        ${res.net_benefit:,.2f}")
                typer.echo(
                    f"Payback Period:              {res.payback_period_years or 0:.1f} years"
                )
            else:
                typer.echo(f"Net Economic Benefit: ${res.net_benefit:,.2f}")
                typer.echo(f"Annual Tool Investment: ${res.investment_cost:,.2f}")
            min_roi = res.uncertainty_range.get("min_roi_percentage", 0.0)
            max_roi = res.uncertainty_range.get("max_roi_percentage", 0.0)
            typer.echo(f"Sensitivity Uncertainty: {min_roi:.1f}% to {max_roi:.1f}%")

    @app.command("dora")
    def cli_dora(
        repo: str = typer.Option("firmsoil/gain", "--repo", "-r", help="Repository identifier."),
        env: str = typer.Option("production", "--env", "-e", help="Environment target."),
        json_output: bool = typer.Option(False, "--json", help="Output raw JSON payload."),
    ) -> None:
        """Calculate deterministic DORA metrics from canonical deployment telemetry."""
        from gain.services.dora import DORAService

        configure_logging()
        svc = DORAService()
        res = svc.calculate_dora(repository=repo, environment=env)
        if json_output:
            typer.echo(json.dumps(res.model_dump(mode="json"), indent=2))
        else:
            typer.echo(f"DORA Status: {res.status}")
            if res.status == "available":
                typer.echo(
                    f"Deployment Frequency: {res.deployment_frequency.value} "
                    f"{res.deployment_frequency.unit}"
                )
                typer.echo(f"Change Failure Rate: {res.change_fail_rate.value}%")
                if res.change_lead_time.value is not None:
                    typer.echo(f"Lead Time for Changes: {res.change_lead_time.value}s")
            else:
                for dep in res.missing_dependencies:
                    typer.echo(f"- Missing: {dep}")

    @app.command("issues")
    def cli_issues(
        project: str | None = typer.Option(None, "--project", "-p", help="Project key filter."),
        repo: str | None = typer.Option(None, "--repo", "-r", help="Repository filter."),
        json_output: bool = typer.Option(False, "--json", help="Output raw JSON payload."),
    ) -> None:
        """Analyze canonical work item velocity, cycle times, and PR traceability."""
        from gain.services.issue_analytics import IssueAnalyticsService

        configure_logging()
        svc = IssueAnalyticsService()
        res = svc.analyze_issues(project_key=project, repository=repo)
        if json_output:
            typer.echo(json.dumps(res.model_dump(mode="json"), indent=2))
        else:
            typer.echo(f"Issue Analytics Status: {res.status} ({res.classification})")
            typer.echo(f"Total Issues: {res.total_issues} ({res.resolved_issues} resolved)")
            typer.echo(f"Traceability Rate: {res.traceability_rate}%")
            for f in res.findings:
                typer.echo(f"- {f}")
