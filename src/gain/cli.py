from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
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
agent_app = typer.Typer(help="Engineering Intelligence Agent operations.")
app.add_typer(agent_app, name="agent")


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
    run_id = str(uuid.uuid4())
    structlog.contextvars.bind_contextvars(run_id=run_id)
    result = PullRequestBackfill(settings, _build_client(settings)).run(ingestion_run_id=run_id)
    typer.echo(json.dumps(result, indent=2, sort_keys=True))


@app.command()
def normalize(
    run_id: str = typer.Option(..., help="Ingestion run ID under the raw directory."),
) -> None:
    """Normalize a raw ingestion run into the canonical PR dataset."""
    configure_logging()
    structlog.contextvars.bind_contextvars(run_id=run_id)
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


@app.command("mcp")
def serve_mcp(
    transport: str = typer.Option(
        "stdio",
        "--transport",
        "-t",
        help="MCP transport protocol: 'stdio' (local/dev) or 'streamable-http' (production ASGI).",
    ),
    host: str = typer.Option(
        "127.0.0.1",
        "--host",
        "-h",
        help="Host interface for Streamable HTTP transport.",
    ),
    port: int = typer.Option(
        8000,
        "--port",
        "-p",
        help="Port for Streamable HTTP transport.",
    ),
    path: str = typer.Option(
        "/mcp",
        "--path",
        help="Streamable HTTP endpoint path.",
    ),
) -> None:
    """Run the GAIN Model Context Protocol (MCP) Server."""
    from gain.mcp.server.app import create_mcp_server
    from gain.mcp.transports.http import run_streamable_http
    from gain.mcp.transports.stdio import run_stdio

    server = create_mcp_server()

    if transport == "stdio":
        typer.echo("Starting GAIN MCP Server over stdio transport...", err=True)
        run_stdio(server)
    elif transport in ("streamable-http", "http"):
        typer.echo(
            f"Starting GAIN MCP Server over Streamable HTTP on http://{host}:{port}{path}...",
            err=True,
        )
        run_streamable_http(server, host=host, port=port, streamable_http_path=path)
    else:
        raise typer.BadParameter(
            f"Unsupported transport '{transport}'. Choose 'stdio' or 'streamable-http'."
        )


@agent_app.command("ask")
def agent_ask(
    query: str = typer.Argument(
        ..., help="Natural-language question to ask the Engineering Intelligence Agent."
    ),
    repo: str = typer.Option(
        "firmsoil/gain", "--repo", "-r", help="Target repository name with owner."
    ),
) -> None:
    """Ask an engineering intelligence question with policy guard and evidence verification."""
    import asyncio

    from gain.agent.orchestrator import EngineeringIntelligenceAgent

    agent = EngineeringIntelligenceAgent()
    resp = asyncio.run(agent.investigate(query=query, default_repo=repo))
    typer.echo(resp.summary)


@agent_app.command("investigate")
def agent_investigate(
    query: str = typer.Argument(..., help="Engineering question or hypothesis to investigate."),
    repo: str = typer.Option(
        "firmsoil/gain", "--repo", "-r", help="Target repository name with owner."
    ),
    json_output: bool = typer.Option(False, "--json", help="Output full structured JSON report."),
) -> None:
    """Run an end-to-end multi-step engineering investigation and build an evidence package."""
    import asyncio

    from gain.agent.orchestrator import EngineeringIntelligenceAgent

    agent = EngineeringIntelligenceAgent()
    resp = asyncio.run(agent.investigate(query=query, default_repo=repo))

    if json_output:
        typer.echo(json.dumps(resp.model_dump(mode="json"), indent=2))
    else:
        typer.echo(resp.summary)
        typer.echo("")
        typer.echo(f"Evidence Package: {resp.evidence_package_id}")
        typer.echo(f"Investigation ID: {resp.investigation_id}")
        typer.echo(f"Total Classified Claims: {len(resp.claims)}")


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
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON scenario payload."),
) -> None:
    """Calculate deterministic AI tooling economic ROI and sensitivity scenarios."""
    from gain.services.ai_roi import AIROIService

    configure_logging()
    svc = AIROIService()
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
        typer.echo(f"Net Economic Benefit: ${res.net_benefit:,.2f}")
        typer.echo(f"Annual Tool Investment: ${res.investment_cost:,.2f}")
        min_roi = res.uncertainty_range.get("min_roi_percentage", 0.0)
        max_roi = res.uncertainty_range.get("max_roi_percentage", 0.0)
        typer.echo(f"Sensitivity Uncertainty: {min_roi:.1f}% to {max_roi:.1f}%")


@app.command("ingest-jira")
def cli_ingest_jira(
    file_path: str = typer.Argument(..., help="Path to JSON file containing Jira issues."),
    project: str = typer.Option("default", "--project", "-p", help="Jira project key."),
    json_output: bool = typer.Option(False, "--json", help="Output summary as JSON."),
) -> None:
    """Ingest Jira issues through enterprise source adapter into canonical storage."""
    from pathlib import Path

    from gain.adapters.jira import JiraSourceAdapter

    configure_logging()
    path = Path(file_path)
    if not path.exists():
        typer.echo(f"Error: file not found: {file_path}", err=True)
        raise typer.Exit(1)

    with open(path, encoding="utf-8") as f:
        payloads = json.load(f)
    if not isinstance(payloads, list):
        payloads = [payloads]

    adapter = JiraSourceAdapter()
    result = adapter.ingest_payloads(payloads, partition_key=project)
    if json_output:
        typer.echo(json.dumps(result.model_dump(mode="json"), indent=2))
    else:
        typer.echo(
            f"Jira Ingestion Complete: {result.canonical_records_count} issues canonicalized"
        )
        typer.echo(f"Quarantined Errors: {result.errors_count}")
        typer.echo(f"Canonical Storage: {result.canonical_file_path}")


@app.command("ingest-linear")
def cli_ingest_linear(
    file_path: str = typer.Argument(..., help="Path to JSON file containing Linear issues."),
    team: str = typer.Option("default", "--team", "-t", help="Linear team key."),
    json_output: bool = typer.Option(False, "--json", help="Output summary as JSON."),
) -> None:
    """Ingest Linear issues through enterprise source adapter into canonical storage."""
    from pathlib import Path

    from gain.adapters.linear import LinearSourceAdapter

    configure_logging()
    path = Path(file_path)
    if not path.exists():
        typer.echo(f"Error: file not found: {file_path}", err=True)
        raise typer.Exit(1)

    with open(path, encoding="utf-8") as f:
        payloads = json.load(f)
    if not isinstance(payloads, list):
        payloads = [payloads]

    adapter = LinearSourceAdapter()
    result = adapter.ingest_payloads(payloads, partition_key=team)
    if json_output:
        typer.echo(json.dumps(result.model_dump(mode="json"), indent=2))
    else:
        typer.echo(
            f"Linear Ingestion Complete: {result.canonical_records_count} issues canonicalized"
        )
        typer.echo(f"Quarantined Errors: {result.errors_count}")


@app.command("ingest-deployments")
def cli_ingest_deployments(
    file_path: str = typer.Argument(..., help="Path to JSON file containing deployment events."),
    repo: str = typer.Option("firmsoil/gain", "--repo", "-r", help="Repository identifier."),
    json_output: bool = typer.Option(False, "--json", help="Output summary as JSON."),
) -> None:
    """Ingest CI/CD deployment events into canonical storage."""
    from pathlib import Path

    from gain.adapters.deployments import DeploymentSourceAdapter

    configure_logging()
    path = Path(file_path)
    if not path.exists():
        typer.echo(f"Error: file not found: {file_path}", err=True)
        raise typer.Exit(1)

    with open(path, encoding="utf-8") as f:
        payloads = json.load(f)
    if not isinstance(payloads, list):
        payloads = [payloads]

    adapter = DeploymentSourceAdapter()
    result = adapter.ingest_payloads(payloads, partition_key=repo.replace("/", "__"))
    if json_output:
        typer.echo(json.dumps(result.model_dump(mode="json"), indent=2))
    else:
        typer.echo(
            f"Deployment Ingestion Complete: {result.canonical_records_count} "
            "deployments canonicalized"
        )
        typer.echo(f"Quarantined Errors: {result.errors_count}")


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


@app.command("demo")
def cli_demo(
    data_dir: Path | None = typer.Option(
        None,
        "--data-dir",
        "-d",
        help="Optional destination root directory for synthetic demo data.",
    ),
) -> None:
    """Run an end-to-end interactive demo across all GAIN capabilities using synthetic telemetry."""
    import importlib.util
    import sys

    scripts_dir = Path(__file__).resolve().parent.parent.parent / "scripts"
    demo_path = scripts_dir / "demo_gain_platform.py"
    if not demo_path.is_file():
        typer.echo(f"Error: Demo script not found at {demo_path}", err=True)
        raise typer.Exit(code=1)

    spec = importlib.util.spec_from_file_location("demo_gain_platform", demo_path)
    if spec is None or spec.loader is None:
        typer.echo("Error: Unable to load demo script", err=True)
        raise typer.Exit(code=1)

    module = importlib.util.module_from_spec(spec)
    sys.modules["demo_gain_platform"] = module
    spec.loader.exec_module(module)
    module.run_demo(data_root=data_dir)


if __name__ == "__main__":
    app()
