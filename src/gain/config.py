from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from gain.errors import ConfigurationError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GAIN_", env_file=".env", extra="ignore")

    github_api_url: str = "https://api.github.com/graphql"
    github_token: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "GAIN_GITHUB_TOKEN", "GITHUB_TOKEN", "gain_github_token", "github_token"
        ),
    )
    github_repos: list[str] | str = Field(default_factory=list)
    start_at: datetime = Field(
        default_factory=lambda: datetime(2025, 9, 1, tzinfo=UTC)
    )
    end_at: datetime = Field(
        default_factory=lambda: datetime(2026, 9, 1, tzinfo=UTC)
    )
    output_dir: Path = Path("./data")
    raw_dir: Path = Path("./data/raw")
    canonical_dir: Path = Path("./data/canonical")
    metrics_dir: Path = Path("./data/metrics")
    requirements_dir: Path = Path("./data/requirements")
    specification_seed_dir: Path = Path("./data/specification-seeds")
    page_size: int = Field(default=50, ge=1, le=100)
    max_retries: int = Field(default=4, ge=0, le=10)
    base_backoff_seconds: float = Field(default=1.0, gt=0)
    retry_max_backoff_seconds: float = Field(default=30.0, gt=0)
    include_bots: bool = False
    requirements_llm_provider: str | None = None
    requirements_llm_model: str | None = None
    requirements_prompt_template_version: str = "story-generation-v1"
    jira_base_url: str | None = None
    jira_token: str | None = None
    jira_project_key: str | None = None
    jira_story_points_field_id: str | None = None
    jira_sprint_field_id: str | None = None
    jira_description_format: str = "adf"
    jira_timeout_seconds: float = Field(default=30.0, gt=0)
    jira_max_retries: int = Field(default=3, ge=0, le=10)

    @field_validator("github_repos", mode="before")
    @classmethod
    def parse_repos(cls, value: object) -> list[str]:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        raise ValueError("github_repos must be a comma-separated string or list")

    def validate_runtime(self) -> None:
        if self.end_at <= self.start_at:
            raise ConfigurationError("end_at must be later than start_at")
        if not self.github_token:
            raise ConfigurationError("GITHUB_TOKEN is required")
        if not self.github_repos:
            raise ConfigurationError("GAIN_GITHUB_REPOS must contain at least one owner/repository")
        for repo in self.github_repos:
            if repo.count("/") != 1 or any(not part for part in repo.split("/")):
                raise ConfigurationError(f"Invalid repository '{repo}'; expected owner/name")

    def ensure_directories(self) -> None:
        for directory in (
            self.output_dir,
            self.raw_dir,
            self.canonical_dir,
            self.metrics_dir,
            self.requirements_dir,
            self.specification_seed_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def validate_jira_runtime(self) -> None:
        if not self.jira_base_url:
            raise ConfigurationError("GAIN_JIRA_BASE_URL is required for Jira synchronization")
        if not self.jira_token:
            raise ConfigurationError("GAIN_JIRA_TOKEN is required for Jira synchronization")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
