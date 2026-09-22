from __future__ import annotations

import json
from pathlib import Path

import typer

from gain.config import Settings
from gain.github.client import GitHubGraphQLClient
from gain.requirements.jira import (
    JiraDescriptionFormat,
    JiraFieldConfiguration,
    JiraStoryMapper,
)
from gain.requirements.service import RequirementsService
from gain.requirements.storage import RequirementsStore, SpecificationSeedStore


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
