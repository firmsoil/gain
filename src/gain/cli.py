from __future__ import annotations

import json
from datetime import UTC, datetime, timezone
from pathlib import Path

import typer

from gain.config import Settings, get_settings
from gain.github.client import GitHubGraphQLClient
from gain.logging import configure_logging
from gain.metrics.catalog import MetricCatalog
from gain.metrics.cycle_time import CycleTimeMetric
from gain.metrics.monthly_stats import MonthlyStatsMetric
from gain.quality import validate_pull_requests
from gain.requirements.generation import StaticStoryProvider
from gain.requirements.jira import (
    JiraAdapter,
    JiraDescriptionFormat,
    JiraFieldConfiguration,
    JiraStoryMapper,
    JiraSynchronizationService,
)
from gain.requirements.models import BusinessContext, RequirementEvent
from gain.requirements.service import RequirementsService
from gain.requirements.storage import RequirementsStore, SpecificationSeedStore
from gain.schema import normalize_records
from gain.storage.analytics import (
    read_canonical,
    write_canonical,
    write_cycle_time_observations,
    write_monthly_stats,
)
from gain.storage.raw import RawStore
from gain.sync import PullRequestBackfill

app = typer.Typer(help="GAIN — GitHub AI Intelligence Network")
requirements_app = typer.Typer(help="Human-governed requirements → Jira → SDD operations.")
app.add_typer(requirements_app, name="requirements")


def _build_client(settings: Settings) -> GitHubGraphQLClient:
    assert settings.github_token is not None
    return GitHubGraphQLClient(
        token=settings.github_token,
        api_url=settings.github_api_url,
        page_size=settings.page_size,
        max_retries=settings.max_retries,
        base_backoff_seconds=settings.base_backoff_seconds,
        retry_max_backoff_seconds=settings.retry_max_backoff_seconds,
    )


def _requirements_service(settings: Settings) -> RequirementsService:
    return RequirementsService(
        RequirementsStore(settings.requirements_dir),
        seed_store=SpecificationSeedStore(settings.specification_seed_dir),
    )


def _load_json(path: Path) -> dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise typer.BadParameter(f"Could not read JSON from {path}") from exc
    if not isinstance(data, dict):
        raise typer.BadParameter(f"Expected a JSON object in {path}")
    return data


def _requirements_mapper(settings: Settings) -> JiraStoryMapper:
    try:
        description_format = JiraDescriptionFormat(settings.jira_description_format.lower())
    except ValueError as exc:
        raise typer.BadParameter("GAIN_JIRA_DESCRIPTION_FORMAT must be 'adf' or 'wiki'") from exc
    return JiraStoryMapper(
        JiraFieldConfiguration(
            description_format=description_format,
            default_project_key=settings.jira_project_key,
            story_points_field_id=settings.jira_story_points_field_id,
            sprint_field_id=settings.jira_sprint_field_id,
        )
    )


@app.command("config-check")
def config_check() -> None:
    """Validate runtime configuration without contacting GitHub."""
    configure_logging()
    settings = get_settings()
    settings.validate_runtime()
    typer.echo("GAIN configuration OK")
    typer.echo(f"repositories={','.join(settings.github_repos)}")
    typer.echo(f"window={settings.start_at.isoformat()}..{settings.end_at.isoformat()}")


@app.command()
def backfill() -> None:
    """Backfill PRs from GitHub GraphQL into replayable raw storage."""
    configure_logging()
    settings = get_settings()
    settings.validate_runtime()
    settings.ensure_directories()
    result = PullRequestBackfill(settings, _build_client(settings)).run()
    typer.echo(json.dumps(result, indent=2, sort_keys=True))


@app.command()
def normalize(
    run_id: str = typer.Option(..., help="Ingestion run ID under the raw directory."),
) -> None:
    """Normalize a raw ingestion run into the canonical PR dataset."""
    configure_logging()
    settings = get_settings()
    settings.ensure_directories()
    raw_records = RawStore(settings.raw_dir).read_run(run_id)
    prs, errors = normalize_records(raw_records)
    quality_issues = validate_pull_requests(prs)
    canonical_path = settings.canonical_dir / f"pull_requests__{run_id}.parquet"
    write_canonical(prs, canonical_path)
    report = {
        "run_id": run_id,
        "raw_records": len(raw_records),
        "canonical_records": len(prs),
        "normalization_errors": errors,
        "quality_issues": [issue.__dict__ for issue in quality_issues],
        "canonical_path": str(canonical_path),
    }
    report_path = settings.output_dir / f"normalization_report__{run_id}.json"
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    typer.echo(json.dumps(report, indent=2, default=str))


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
        raise typer.BadParameter("Code and Metric Catalog versions do not match for GAIN-PR-001")
    prs = read_canonical(canonical_path)
    observations = CycleTimeMetric.observations(prs)
    output_path = settings.metrics_dir / "gain-pr-001-cycle-time.parquet"
    write_cycle_time_observations(observations, output_path)
    summary = CycleTimeMetric.summary(observations)
    summary["metric_id"] = CycleTimeMetric.metric_id
    summary["metric_version"] = CycleTimeMetric.metric_version
    summary["generated_at"] = datetime.now(timezone.utc).isoformat()
    summary_path = settings.metrics_dir / "gain-pr-001-cycle-time-summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    typer.echo(json.dumps(summary, indent=2, sort_keys=True, default=str))


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


@requirements_app.command("create-context")
def create_context(
    input_file: Path = typer.Option(..., exists=True, dir_okay=False, readable=True),
    actor: str | None = typer.Option(None),
) -> None:
    """Persist structured, human-supplied business context."""
    settings = get_settings()
    settings.ensure_directories()
    context = BusinessContext.model_validate(_load_json(input_file))
    saved = _requirements_service(settings).create_context(context, actor)
    typer.echo(json.dumps(saved.model_dump(mode="json"), indent=2, sort_keys=True))


@requirements_app.command("revise-context")
def revise_context(
    context_id: str = typer.Option(...),
    changes: Path = typer.Option(..., exists=True, dir_okay=False, readable=True),
    actor: str = typer.Option(...),
) -> None:
    """Version Business Analyst context before regenerating a story."""
    settings = get_settings()
    settings.ensure_directories()
    context = _requirements_service(settings).revise_context(
        context_id,
        _load_json(changes),
        actor=actor,
    )
    typer.echo(json.dumps(context.model_dump(mode="json"), indent=2, sort_keys=True))


@requirements_app.command("generate-story")
def generate_story(
    context_id: str = typer.Option(...),
    structured_output: Path = typer.Option(..., exists=True, dir_okay=False, readable=True),
    actor: str | None = typer.Option(None),
) -> None:
    """Validate structured provider output and save it as a non-authoritative draft.

    A production LLM client implements StoryGenerationProvider and calls the same service boundary.
    This command intentionally accepts a JSON result so operators can use any approved provider.
    """
    settings = get_settings()
    settings.ensure_directories()
    provider = StaticStoryProvider(_load_json(structured_output))
    story = _requirements_service(settings).generate_story(context_id, provider, actor=actor)
    typer.echo(json.dumps(story.model_dump(mode="json"), indent=2, sort_keys=True))


@requirements_app.command("validate-story")
def validate_story(story_id: str = typer.Option(...)) -> None:
    """Report deterministic hard errors and advisory warnings for a story version."""
    settings = get_settings()
    report = _requirements_service(settings).validate_stored_story(story_id)
    typer.echo(
        json.dumps(
            {
                "valid": report.is_valid,
                "errors": [issue.__dict__ for issue in report.errors],
                "warnings": [issue.__dict__ for issue in report.warnings],
            },
            indent=2,
            default=str,
        )
    )


@requirements_app.command("regenerate-story")
def regenerate_story(
    story_id: str = typer.Option(...),
    structured_output: Path = typer.Option(..., exists=True, dir_okay=False, readable=True),
    actor: str | None = typer.Option(None),
) -> None:
    """Save a new AI draft version; it must be reviewed again before approval."""
    settings = get_settings()
    settings.ensure_directories()
    story = _requirements_service(settings).regenerate_story(
        story_id,
        StaticStoryProvider(_load_json(structured_output)),
        actor=actor,
    )
    typer.echo(json.dumps(story.model_dump(mode="json"), indent=2, sort_keys=True))


@requirements_app.command("review-story")
def review_story(story_id: str = typer.Option(...), reviewer: str = typer.Option(...)) -> None:
    """Record assignment of a draft to a named human reviewer."""
    settings = get_settings()
    settings.ensure_directories()
    story = _requirements_service(settings).request_review(story_id, reviewer)
    typer.echo(json.dumps(story.model_dump(mode="json"), indent=2, sort_keys=True))


@requirements_app.command("revise-story")
def revise_story(
    story_id: str = typer.Option(...),
    changes: Path = typer.Option(..., exists=True, dir_okay=False, readable=True),
    reviewer: str = typer.Option(...),
    reason: str = typer.Option("human_revision"),
) -> None:
    """Apply human edits as a new DRAFT version, preserving all prior versions."""
    settings = get_settings()
    settings.ensure_directories()
    story = _requirements_service(settings).revise_story(
        story_id, _load_json(changes), reviewer=reviewer, reason=reason
    )
    typer.echo(json.dumps(story.model_dump(mode="json"), indent=2, sort_keys=True))


@requirements_app.command("approve-story")
def approve_story(story_id: str = typer.Option(...), reviewer: str = typer.Option(...)) -> None:
    """Create an explicitly human-approved version after deterministic validation."""
    settings = get_settings()
    settings.ensure_directories()
    story = _requirements_service(settings).approve_story(story_id, reviewer)
    typer.echo(json.dumps(story.model_dump(mode="json"), indent=2, sort_keys=True))


@requirements_app.command("reject-story")
def reject_story(
    story_id: str = typer.Option(...),
    reviewer: str = typer.Option(...),
    reason: str = typer.Option(...),
) -> None:
    """Record a reviewer rejection as a new immutable version."""
    settings = get_settings()
    settings.ensure_directories()
    story = _requirements_service(settings).reject_story(story_id, reviewer, reason)
    typer.echo(json.dumps(story.model_dump(mode="json"), indent=2, sort_keys=True))


@requirements_app.command("show-history")
def show_history(story_id: str = typer.Option(...)) -> None:
    """Show each immutable revision without modifying the story."""
    settings = get_settings()
    history = RequirementsStore(settings.requirements_dir).story_history(story_id)
    typer.echo(
        json.dumps([story.model_dump(mode="json") for story in history], indent=2, sort_keys=True)
    )


@requirements_app.command("jira-payload")
def jira_payload(story_id: str = typer.Option(...)) -> None:
    """Render a validated approved story to provider-specific Jira fields without calling Jira."""
    settings = get_settings()
    story = RequirementsStore(settings.requirements_dir).get_story(story_id)
    if not story.is_authoritative_requirement:
        raise typer.BadParameter("Only an approved story may be rendered for Jira export")
    typer.echo(
        json.dumps(_requirements_mapper(settings).to_payload(story), indent=2, sort_keys=True)
    )


@requirements_app.command("import-jira-story")
def import_jira_story(
    issue: Path = typer.Option(..., exists=True, dir_okay=False, readable=True),
    context_id: str = typer.Option(...),
) -> None:
    """Normalize a Jira issue into a DRAFT; imported content is never implicitly approved."""
    settings = get_settings()
    settings.ensure_directories()
    store = RequirementsStore(settings.requirements_dir)
    context = store.get_context(context_id)
    story = _requirements_mapper(settings).from_jira_issue(
        _load_json(issue),
        source_context_id=context.context_id,
        source_context_version=context.version,
    )
    store.save_story(story)
    store.append_event(
        RequirementEvent(
            event_type="jira_imported",
            context_id=context.context_id,
            story_id=story.story_id,
            story_version=story.version,
        )
    )
    typer.echo(json.dumps(story.model_dump(mode="json"), indent=2, sort_keys=True))


@requirements_app.command("sync-jira")
def sync_jira(story_id: str = typer.Option(...)) -> None:
    """Create or update the matching Jira issue for an approved story."""
    settings = get_settings()
    settings.validate_jira_runtime()
    settings.ensure_directories()
    assert settings.jira_base_url is not None
    assert settings.jira_token is not None
    adapter = JiraAdapter(
        settings.jira_base_url,
        settings.jira_token,
        timeout_seconds=settings.jira_timeout_seconds,
        max_retries=settings.jira_max_retries,
    )
    store = RequirementsStore(settings.requirements_dir)
    story = store.get_story(story_id)
    synchronized = JiraSynchronizationService(_requirements_mapper(settings), store).synchronize(
        story, adapter
    )
    typer.echo(json.dumps(synchronized.model_dump(mode="json"), indent=2, sort_keys=True))


@requirements_app.command("promote-story")
def promote_story(story_id: str = typer.Option(...)) -> None:
    """Create an SDD specification seed from an approved story; it is not a formal spec."""
    settings = get_settings()
    settings.ensure_directories()
    seed = _requirements_service(settings).promote_story(story_id)
    typer.echo(json.dumps(seed.model_dump(mode="json"), indent=2, sort_keys=True))


@requirements_app.command("show-traceability")
def show_traceability(story_id: str = typer.Option(...)) -> None:
    """Show the persisted context, Jira identity, and SDD seeds linked to a story."""
    settings = get_settings()
    store = RequirementsStore(settings.requirements_dir)
    story = store.get_story(story_id)
    context = store.get_context(story.source_context_id, story.source_context_version)
    seeds = SpecificationSeedStore(settings.specification_seed_dir).find_for_story(story_id)
    typer.echo(
        json.dumps(
            {
                "canonical_requirement": {
                    "requirement_id": story.requirement_id,
                    "version": story.version,
                    "lifecycle_status": story.lifecycle_status,
                },
                "business_context": {
                    "context_id": context.context_id,
                    "version": context.version,
                },
                "story": {"story_id": story.story_id, "version": story.version},
                "external_references": [
                    ref.model_dump(mode="json") for ref in story.external_references
                ],
                "jira_issue": {
                    "external_system": story.external_system,
                    "project_key": story.project_key,
                    "issue_id": story.external_issue_id,
                    "issue_key": story.external_issue_key,
                    "url": story.external_url,
                },
                "sdd_specification_seeds": [
                    {
                        "promotion_id": seed.promotion_id,
                        "story_version": seed.story_version,
                        "created_at": seed.created_at,
                    }
                    for seed in seeds
                ],
                "formal_specification_id": story.parent_spec_id,
            },
            indent=2,
            sort_keys=True,
            default=str,
        )

    )


@requirements_app.command("link-specification")
def link_specification(
    story_id: str = typer.Option(...),
    specification_id: str = typer.Option(...),
    actor: str = typer.Option(...),
) -> None:
    """Link the approved story to the formal SDD specification produced downstream."""
    settings = get_settings()
    settings.ensure_directories()
    story = _requirements_service(settings).link_formal_specification(
        story_id,
        specification_id,
        actor=actor,
    )
    typer.echo(json.dumps(story.model_dump(mode="json"), indent=2, sort_keys=True))


if __name__ == "__main__":
    app()
