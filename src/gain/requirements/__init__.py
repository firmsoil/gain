"""Human-governed, Jira-compatible requirements engineering for GAIN.

This package is intentionally independent from GitHub acquisition and analytics.
"""

from gain.requirements.models import (
    AcceptanceCriterion,
    BusinessContext,
    CanonicalRequirement,
    CanonicalStory,
    CriterionValidationStatus,
    ExternalReference,
    GeneratedRequirementDraft,
    GeneratedStory,
    IssueType,
    RequirementEvent,
    RequirementLifecycleStatus,
    RequirementType,
    SDDSpecificationSeed,
    StoryLifecycleStatus,
)

__all__ = [
    "AcceptanceCriterion",
    "BusinessContext",
    "CanonicalRequirement",
    "CanonicalStory",
    "CriterionValidationStatus",
    "ExternalReference",
    "GeneratedRequirementDraft",
    "GeneratedStory",
    "IssueType",
    "RequirementEvent",
    "RequirementLifecycleStatus",
    "RequirementType",
    "SDDSpecificationSeed",
    "StoryLifecycleStatus",
]

