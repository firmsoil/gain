from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from gain.requirements.models import CanonicalStory


class IssueSeverity(StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"


@dataclass(frozen=True)
class StoryQualityIssue:
    code: str
    severity: IssueSeverity
    message: str
    criterion_id: str | None = None


@dataclass(frozen=True)
class StoryQualityReport:
    issues: tuple[StoryQualityIssue, ...]

    @property
    def errors(self) -> tuple[StoryQualityIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == IssueSeverity.ERROR)

    @property
    def warnings(self) -> tuple[StoryQualityIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == IssueSeverity.WARNING)

    @property
    def is_valid(self) -> bool:
        return not self.errors


_AMBIGUOUS_WORDS = re.compile(r"\b(?:etc\.?|tbd|maybe|somehow|user-friendly|fast|quickly)\b", re.I)
_NUMBER = re.compile(r"\b\d+(?:\.\d+)?\b")


def validate_story_quality(story: CanonicalStory) -> StoryQualityReport:
    issues: list[StoryQualityIssue] = []

    required = {
        "summary": story.summary,
        "role": story.role,
        "capability": story.capability,
        "business_value": story.business_value,
        "description": story.description,
    }
    for field, value in required.items():
        if not value.strip():
            issues.append(
                StoryQualityIssue(f"missing_{field}", IssueSeverity.ERROR, f"{field} is required")
            )

    if not story.acceptance_criteria:
        issues.append(
            StoryQualityIssue(
                "missing_acceptance_criteria",
                IssueSeverity.ERROR,
                "At least one acceptance criterion is required",
            )
        )

    seen_criteria: set[tuple[str, str, str]] = set()
    for criterion in story.acceptance_criteria:
        fields = {"given": criterion.given, "when": criterion.when, "then": criterion.then}
        for name, value in fields.items():
            if not value.strip():
                issues.append(
                    StoryQualityIssue(
                        "malformed_given_when_then",
                        IssueSeverity.ERROR,
                        f"Acceptance criterion is missing {name}",
                        criterion.criterion_id,
                    )
                )
        fingerprint: tuple[str, str, str] = (
            fields["given"].strip().casefold(),
            fields["when"].strip().casefold(),
            fields["then"].strip().casefold(),
        )
        if fingerprint in seen_criteria:
            issues.append(
                StoryQualityIssue(
                    "duplicate_acceptance_criterion",
                    IssueSeverity.ERROR,
                    "Duplicate Given/When/Then acceptance criterion",
                    criterion.criterion_id,
                )
            )
        seen_criteria.add(fingerprint)

    if story.open_questions:
        issues.append(
            StoryQualityIssue(
                "unresolved_open_questions",
                IssueSeverity.ERROR,
                "Material open questions must be resolved before approval",
            )
        )
    if story.ambiguity_flags:
        issues.append(
            StoryQualityIssue(
                "ambiguity_flags_present",
                IssueSeverity.WARNING,
                "Story retains ambiguity flags for reviewer attention",
            )
        )

    all_text = " ".join(
        [
            story.summary,
            story.description,
            story.role,
            story.capability,
            story.business_value,
            *story.preconditions,
            *(criterion.given for criterion in story.acceptance_criteria),
            *(criterion.when for criterion in story.acceptance_criteria),
            *(criterion.then for criterion in story.acceptance_criteria),
        ]
    )
    if _AMBIGUOUS_WORDS.search(all_text):
        issues.append(
            StoryQualityIssue(
                "ambiguous_wording",
                IssueSeverity.WARNING,
                "Story contains wording that should be made observable before implementation",
            )
        )
    if _NUMBER.search(all_text):
        issues.append(
            StoryQualityIssue(
                "quantitative_claim_review",
                IssueSeverity.WARNING,
                "Quantitative claims require reviewer confirmation against business context",
            )
        )

    return StoryQualityReport(tuple(issues))
