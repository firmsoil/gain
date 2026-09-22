from __future__ import annotations

from datetime import UTC, datetime

import pytest

from gain.config import Settings
from gain.errors import ConfigurationError


def test_default_settings_construction() -> None:
    settings = Settings()
    assert settings.github_api_url == "https://api.github.com/graphql"


def test_environment_defaults_to_development() -> None:
    settings = Settings()
    assert settings.environment == "development"


def test_validate_production_readiness_raises_without_token() -> None:
    settings = Settings(environment="production", github_token=None)
    with pytest.raises(ConfigurationError, match="GITHUB_TOKEN is required in production"):
        settings.validate_production_readiness()


def test_validate_production_readiness_passes_in_development() -> None:
    settings = Settings(environment="development", github_token=None)
    # Should not raise
    settings.validate_production_readiness()


def test_config_merge_with_defaults() -> None:
    settings = Settings(github_repos="owner/repo1, owner/repo2,owner/repo3")
    assert settings.github_repos == ["owner/repo1", "owner/repo2", "owner/repo3"]


def test_parse_repos_list() -> None:
    settings = Settings(github_repos=["owner/repo1", "owner/repo2"])
    assert settings.github_repos == ["owner/repo1", "owner/repo2"]


def test_validate_runtime_raises_on_invalid_repo() -> None:
    settings = Settings(
        github_token="fake_token",
        github_repos=["owner_only"],
        start_at=datetime(2023, 1, 1, tzinfo=UTC),
        end_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    with pytest.raises(
        ConfigurationError, match="Invalid repository 'owner_only'; expected owner/name"
    ):
        settings.validate_runtime()

    settings = Settings(
        github_token="fake_token",
        github_repos=["owner/repo/extra"],
        start_at=datetime(2023, 1, 1, tzinfo=UTC),
        end_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    with pytest.raises(
        ConfigurationError, match="Invalid repository 'owner/repo/extra'; expected owner/name"
    ):
        settings.validate_runtime()


def test_validate_runtime_raises_when_end_at_before_start_at() -> None:
    settings = Settings(
        github_token="fake_token",
        github_repos=["owner/repo"],
        start_at=datetime(2024, 1, 1, tzinfo=UTC),
        end_at=datetime(2023, 1, 1, tzinfo=UTC),
    )
    with pytest.raises(ConfigurationError, match="end_at must be later than start_at"):
        settings.validate_runtime()

    settings = Settings(
        github_token="fake_token",
        github_repos=["owner/repo"],
        start_at=datetime(2024, 1, 1, tzinfo=UTC),
        end_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    with pytest.raises(ConfigurationError, match="end_at must be later than start_at"):
        settings.validate_runtime()


def test_invalid_environment_raises_validation_error() -> None:
    with pytest.raises(ValueError, match="Invalid environment 'unknown_env'"):
        Settings(environment="unknown_env")


def test_invalid_queue_backend_raises_validation_error() -> None:
    with pytest.raises(ValueError, match="queue_backend must be 'in_process' or 'redis'"):
        Settings(queue_backend="kafka")


def test_production_readiness_validates_pii_salt() -> None:
    # Enabled masking with short salt raises ConfigurationError
    settings = Settings(
        environment="production",
        github_token="fake_token",
        github_repos=["owner/repo"],
        pii_mask_authors=True,
        pii_hmac_salt="too_short",
    )
    with pytest.raises(
        ConfigurationError,
        match="GAIN_PII_HMAC_SALT must be at least 16 characters in production",
    ):
        settings.validate_production_readiness()

    # Enabled masking with valid >=16 chars salt passes
    settings_valid = Settings(
        environment="production",
        github_token="fake_token",
        github_repos=["owner/repo"],
        pii_mask_authors=True,
        pii_hmac_salt="very_secure_enterprise_salt_12345",
    )
    settings_valid.validate_production_readiness()
