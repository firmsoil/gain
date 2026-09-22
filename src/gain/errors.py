from __future__ import annotations

from typing import Any


class GainError(Exception):
    """Base exception for GAIN."""

    error_code: str = "GAIN-0000"
    is_retryable: bool = False
    severity: str = "ERROR"
    team: str = "platform"

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ConfigurationError(GainError):
    """Raised when environment variables, options, or credentials are invalid or missing."""

    error_code: str = "GAIN-1001"
    team: str = "platform"


class GitHubApiError(GainError):
    """Raised when GitHub GraphQL API requests encounter transport or execution errors."""

    error_code: str = "GAIN-2001"
    team: str = "platform"


class RateLimitError(GitHubApiError):
    """Raised when GitHub rate-limiting quotas are exhausted and cannot be immediately serviced."""

    error_code: str = "GAIN-2029"
    is_retryable: bool = True


class IncompletePaginationError(GitHubApiError):
    """Raised when cursor pagination halts prematurely or returns an identical cursor."""

    error_code: str = "GAIN-2002"


class DataQualityError(GainError):
    """Raised when telemetric data fails schema validation or contains corruptions."""

    error_code: str = "GAIN-3001"
    team: str = "data"


class RequirementsError(GainError):
    """Base error for the human-governed requirements subsystem."""

    error_code: str = "GAIN-4001"
    team: str = "data"


class RequirementValidationError(RequirementsError):
    """Raised when a user story or acceptance criterion fails semantic validation."""

    error_code: str = "GAIN-4002"


class InvalidLifecycleTransitionError(RequirementsError):
    """Raised when an illegal transition is attempted on a requirement's lifecycle state."""

    error_code: str = "GAIN-4003"


class JiraIntegrationError(RequirementsError):
    """Raised when an operation against an upstream Jira instance encounters a failure."""

    error_code: str = "GAIN-5001"
    team: str = "platform"


class JiraAuthenticationError(JiraIntegrationError):
    """Raised when credentials or tokens for Jira synchronization fail authentication."""

    error_code: str = "GAIN-5002"
