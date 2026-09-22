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
    github_auth_mode: str = "pat"  # "pat" or "app"
    github_app_id: str | None = None
    github_app_private_key_path: Path | None = None
    github_installation_ids: list[int] = Field(default_factory=list)
    environment: str = Field(default="development")
    github_repos: list[str] | str = Field(default_factory=list)
    start_at: datetime = Field(default_factory=lambda: datetime(2025, 9, 1, tzinfo=UTC))
    end_at: datetime = Field(default_factory=lambda: datetime(2026, 9, 1, tzinfo=UTC))
    data_dir: Path = Path("./data")
    output_dir: Path = Path("./data")
    raw_dir: Path = Path("./data/raw")
    canonical_dir: Path = Path("./data/canonical")
    metrics_dir: Path = Path("./data/metrics")
    requirements_dir: Path = Path("./data/requirements")
    specification_seed_dir: Path = Path("./data/specification-seeds")
    indexes_dir: Path = Path("./data/indexes")
    registry_path: Path = Path("./data/registry.parquet")
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
    pii_mask_authors: bool = False
    pii_hmac_salt: str = ""
    queue_backend: str = "in_process"  # "in_process" or "redis"
    redis_url: str = "redis://localhost:6379/0"

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, value: str) -> str:
        env = value.lower().strip()
        allowed = {"development", "dev", "test", "staging", "stage", "production", "prod"}
        if env not in allowed:
            raise ValueError(f"Invalid environment '{value}'. Allowed: {sorted(allowed)}")
        return env

    @field_validator("queue_backend")
    @classmethod
    def validate_queue_backend(cls, value: str) -> str:
        backend = value.lower().strip()
        if backend not in {"in_process", "redis"}:
            raise ValueError(f"queue_backend must be 'in_process' or 'redis', got '{value}'")
        return backend

    @field_validator("github_auth_mode")
    @classmethod
    def validate_auth_mode(cls, value: str) -> str:
        mode = value.lower().strip()
        if mode not in {"pat", "app"}:
            raise ValueError(f"github_auth_mode must be 'pat' or 'app', got '{value}'")
        return mode

    @field_validator("github_installation_ids", mode="before")
    @classmethod
    def parse_installation_ids(cls, value: object) -> list[int]:
        if value is None or value == "":
            return []
        if isinstance(value, (int, float)):
            return [int(value)]
        if isinstance(value, str):
            return [int(item.strip()) for item in value.split(",") if item.strip()]
        if isinstance(value, list):
            return [int(item) for item in value]
        raise ValueError("github_installation_ids must be a comma-separated string, int, or list")

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
        if self.github_auth_mode == "app":
            if not self.github_app_id:
                raise ConfigurationError(
                    "GAIN_GITHUB_APP_ID is required when github_auth_mode='app'"
                )
            if not self.github_app_private_key_path:
                raise ConfigurationError(
                    "GAIN_GITHUB_APP_PRIVATE_KEY_PATH is required when github_auth_mode='app'"
                )
            if not self.github_installation_ids:
                raise ConfigurationError(
                    "GAIN_GITHUB_INSTALLATION_IDS is required when github_auth_mode='app'"
                )
        else:
            if not self.github_token:
                raise ConfigurationError("GITHUB_TOKEN is required")
        if not self.github_repos:
            raise ConfigurationError("GAIN_GITHUB_REPOS must contain at least one owner/repository")
        for repo in self.github_repos:
            if repo.count("/") != 1 or any(not part for part in repo.split("/")):
                raise ConfigurationError(f"Invalid repository '{repo}'; expected owner/name")

    def validate_production_readiness(self) -> None:
        env_norm = self.environment.lower().strip()
        if env_norm in {"production", "prod"}:
            if self.github_auth_mode == "app":
                if not (
                    self.github_app_id
                    and self.github_app_private_key_path
                    and self.github_installation_ids
                ):
                    raise ConfigurationError(
                        "GitHub App credentials are required in production "
                        "when github_auth_mode='app'"
                    )
                if not self.github_app_private_key_path.is_file():
                    raise ConfigurationError(
                        "GitHub App private key file does not exist: "
                        f"{self.github_app_private_key_path}"
                    )
            elif not self.github_token:
                raise ConfigurationError("GITHUB_TOKEN is required in production")

            if self.pii_mask_authors and (not self.pii_hmac_salt or len(self.pii_hmac_salt) < 16):
                raise ConfigurationError(
                    "GAIN_PII_HMAC_SALT must be at least 16 characters in production "
                    "when author masking is enabled"
                )
            self.validate_runtime()

    def ensure_directories(self) -> None:
        for directory in (
            self.output_dir,
            self.raw_dir,
            self.canonical_dir,
            self.metrics_dir,
            self.requirements_dir,
            self.specification_seed_dir,
            self.indexes_dir,
            self.registry_path.parent,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def validate_jira_runtime(self) -> None:
        if not self.jira_base_url:
            raise ConfigurationError("GAIN_JIRA_BASE_URL is required for Jira synchronization")
        if not self.jira_token:
            raise ConfigurationError("GAIN_JIRA_TOKEN is required for Jira synchronization")


_settings_override: Settings | None = None


def set_settings_override(settings: Settings | None) -> None:
    global _settings_override
    _settings_override = settings


@lru_cache(maxsize=1)
def _default_settings() -> Settings:
    return Settings()


def get_settings() -> Settings:
    if _settings_override is not None:
        return _settings_override
    return _default_settings()
