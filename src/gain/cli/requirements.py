from __future__ import annotations

import json
from pathlib import Path

import typer

from gain.cli.common import _load_json, _requirements_mapper, _requirements_service
from gain.config import get_settings
from gain.requirements.generation import StaticStoryProvider
from gain.requirements.jira import JiraAdapter, JiraSynchronizationService
from gain.requirements.models import BusinessContext, RequirementEvent
from gain.requirements.storage import RequirementsStore, SpecificationSeedStore


def register_requirements_commands(requirements_app: typer.Typer) -> None:
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
        """Validate structured provider output and save it as a non-authoritative draft."""
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
            json.dumps(
                [story.model_dump(mode="json") for story in history], indent=2, sort_keys=True
            )
        )

    @requirements_app.command("jira-payload")
    def jira_payload(story_id: str = typer.Option(...)) -> None:
        """Render a validated approved story to provider-specific Jira fields
        without calling Jira.
        """
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
        synchronized = JiraSynchronizationService(
            _requirements_mapper(settings), store
        ).synchronize(story, adapter)
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
