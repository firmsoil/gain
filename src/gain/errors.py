class GainError(Exception):
    """Base exception for GAIN."""


class ConfigurationError(GainError):
    pass


class GitHubApiError(GainError):
    pass


class RateLimitError(GitHubApiError):
    pass


class IncompletePaginationError(GitHubApiError):
    pass


class DataQualityError(GainError):
    pass


class RequirementsError(GainError):
    """Base error for the human-governed requirements subsystem."""


class RequirementValidationError(RequirementsError):
    pass


class InvalidLifecycleTransitionError(RequirementsError):
    pass


class JiraIntegrationError(RequirementsError):
    pass


class JiraAuthenticationError(JiraIntegrationError):
    pass
