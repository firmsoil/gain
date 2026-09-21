from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid4())


class RequirementType(StrEnum):
    STORY = "Story"
    FEATURE = "Feature"
    TASK = "Task"
    BUG = "Bug"
    EPIC = "Epic"


# Backward-compatible alias for existing code
IssueType = RequirementType


class RequirementLifecycleStatus(StrEnum):
    INTAKE = "INTAKE"
    DRAFT = "DRAFT"
    AI_GENERATED = "AI_GENERATED"
    IN_REVIEW = "IN_REVIEW"
    UNDER_REVIEW = "UNDER_REVIEW"
    REVISED = "REVISED"
    APPROVED = "APPROVED"
    PROMOTED_TO_SPEC = "PROMOTED_TO_SPEC"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


# Backward-compatible alias
StoryLifecycleStatus = RequirementLifecycleStatus


class CriterionValidationStatus(StrEnum):
    UNVALIDATED = "UNVALIDATED"
    VALID = "VALID"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class ExternalReference(BaseModel):
    """Reference to an external work-management or issue-tracking system (e.g., Jira)."""

    model_config = ConfigDict(extra="forbid")

    external_system: str
    external_project: str | None = None
    external_type: str | None = None
    external_id: str | None = None
    external_key: str | None = None
    external_url: str | None = None
    external_version: str | None = None
    last_synced_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class BusinessContext(BaseModel):
    """Structured human-supplied context; it is not an engineering specification."""

    model_config = ConfigDict(extra="forbid")

    context_id: str = Field(default_factory=new_id)
    title: str
    business_problem: str
    business_goal: str
    business_context: str = ""
    stakeholders: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    version: int = Field(default=1, ge=1)


class AcceptanceCriterion(BaseModel):
    """Provider-neutral structured Gherkin criterion."""

    model_config = ConfigDict(extra="forbid")

    criterion_id: str = Field(default_factory=new_id)
    summary: str = ""
    given: str = ""
    when: str = ""
    then: str = ""
    priority: str | None = None
    validation_status: CriterionValidationStatus = CriterionValidationStatus.UNVALIDATED
    and_given: list[str] = Field(default_factory=list)
    and_when: list[str] = Field(default_factory=list)
    and_then: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    notes: str | None = None


class GeneratedRequirementDraft(BaseModel):
    """The provider contract. Pure requirements semantics; external identity is never
    provider supplied."""

    model_config = ConfigDict(extra="forbid")

    summary: str = ""
    description: str = ""
    role: str = ""
    capability: str = ""
    business_value: str = ""
    acceptance_criteria: list[AcceptanceCriterion] = Field(default_factory=list)
    priority: str | None = None
    labels: list[str] = Field(default_factory=list)
    components: list[str] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    ambiguity_flags: list[str] = Field(default_factory=list)
    requirement_type: RequirementType = RequirementType.STORY
    custom_fields: dict[str, Any] = Field(default_factory=dict)

    @field_validator("labels", "components")
    @classmethod
    def unique_values(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(item.strip() for item in value if item.strip()))

    @model_validator(mode="before")
    @classmethod
    def _handle_legacy_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        custom = dict(data.get("custom_fields") or {})

        if "issue_type" in data and "requirement_type" not in data:
            data["requirement_type"] = data.pop("issue_type")

        legacy_fields = [
            "project_key",
            "sprint",
            "story_points",
            "reporter",
            "assignee",
            "parent_id",
            "parent_key",
            "epic_id",
            "epic_key",
            "fix_versions",
            "affects_versions",
            "status",
        ]
        for field in legacy_fields:
            if field in data:
                val = data.pop(field)
                if val is not None:
                    custom[field] = val
                else:
                    custom.pop(field, None)
        data["custom_fields"] = custom
        return data

    @property
    def issue_type(self) -> RequirementType:
        return self.requirement_type

    @property
    def project_key(self) -> str | None:
        val = self.custom_fields.get("project_key")
        return str(val) if val is not None else None

    @property
    def story_points(self) -> float | None:
        val = self.custom_fields.get("story_points")
        return float(val) if val is not None else None

    @property
    def sprint(self) -> str | None:
        val = self.custom_fields.get("sprint")
        return str(val) if val is not None else None

    @property
    def parent_key(self) -> str | None:
        val = self.custom_fields.get("parent_key")
        return str(val) if val is not None else None

    @property
    def epic_key(self) -> str | None:
        val = self.custom_fields.get("epic_key")
        return str(val) if val is not None else None

    @property
    def parent_id(self) -> str | None:
        val = self.custom_fields.get("parent_id")
        return str(val) if val is not None else None

    @property
    def epic_id(self) -> str | None:
        val = self.custom_fields.get("epic_id")
        return str(val) if val is not None else None

    @property
    def reporter(self) -> str | None:
        val = self.custom_fields.get("reporter")
        return str(val) if val is not None else None

    @property
    def assignee(self) -> str | None:
        val = self.custom_fields.get("assignee")
        return str(val) if val is not None else None

    @property
    def fix_versions(self) -> list[str]:
        val = self.custom_fields.get("fix_versions")
        return list(val) if isinstance(val, list) else []

    @property
    def affects_versions(self) -> list[str]:
        val = self.custom_fields.get("affects_versions")
        return list(val) if isinstance(val, list) else []

    @property
    def status(self) -> str | None:
        val = self.custom_fields.get("status")
        return str(val) if val is not None else None


# Backward-compatible alias
GeneratedStory = GeneratedRequirementDraft


class CanonicalRequirement(GeneratedRequirementDraft):
    """The authoritative GAIN canonical requirement domain model independent of external
    trackers."""

    requirement_id: str = Field(default_factory=new_id)
    version: int = Field(default=1, ge=1)
    lifecycle_status: RequirementLifecycleStatus = RequirementLifecycleStatus.DRAFT
    source_context_id: str
    source_context_version: int = Field(ge=1)
    generation_id: str | None = None
    model_provider: str | None = None
    model_name: str | None = None
    model_version: str | None = None
    prompt_template_version: str | None = None
    generation_parameters: dict[str, Any] = Field(default_factory=dict)
    input_hash: str | None = None
    output_hash: str | None = None
    generated_at: datetime | None = None
    reviewed_at: datetime | None = None
    reviewed_by: str | None = None
    approved_at: datetime | None = None
    approved_by: str | None = None
    parent_spec_id: str | None = None
    external_references: list[ExternalReference] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    revision_reason: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _handle_canonical_legacy_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        if "story_id" in data and "requirement_id" not in data:
            data["requirement_id"] = data.pop("story_id")

        external_system = data.pop("external_system", None)
        external_project = data.pop("external_project", None)
        external_issue_id = data.pop("external_issue_id", None)
        external_issue_key = data.pop("external_issue_key", None)
        external_url = data.pop("external_url", None)
        synchronized_at = data.pop("synchronized_at", None)
        external_source_version = data.pop("external_source_version", None)

        references = list(data.get("external_references") or [])
        legacy_external = [
            external_system,
            external_project,
            external_issue_id,
            external_issue_key,
            external_url,
        ]
        if any(legacy_external):
            ref_data = {
                "external_system": external_system or "jira",
                "external_project": external_project,
                "external_id": external_issue_id,
                "external_key": external_issue_key,
                "external_url": external_url,
                "external_version": external_source_version,
                "last_synced_at": synchronized_at,
            }
            references.append(ExternalReference.model_validate(ref_data))
            data["external_references"] = references

        return data

    @property
    def story_id(self) -> str:
        return self.requirement_id

    @property
    def is_authoritative_requirement(self) -> bool:
        return self.lifecycle_status == RequirementLifecycleStatus.APPROVED

    def get_external_reference(self, system: str = "jira") -> ExternalReference | None:
        for ref in self.external_references:
            if ref.external_system == system:
                return ref
        return None

    @property
    def external_system(self) -> str | None:
        ref = self.get_external_reference()
        if ref:
            return ref.external_system
        return self.external_references[0].external_system if self.external_references else None

    @property
    def external_project(self) -> str | None:
        ref = self.get_external_reference()
        return ref.external_project if ref else None

    @property
    def external_issue_id(self) -> str | None:
        ref = self.get_external_reference()
        return ref.external_id if ref else None

    @property
    def external_issue_key(self) -> str | None:
        ref = self.get_external_reference()
        return ref.external_key if ref else None

    @property
    def external_url(self) -> str | None:
        ref = self.get_external_reference()
        return ref.external_url if ref else None

    @property
    def synchronized_at(self) -> datetime | None:
        ref = self.get_external_reference()
        return ref.last_synced_at if ref else None

    @property
    def external_source_version(self) -> str | None:
        ref = self.get_external_reference()
        return ref.external_version if ref else None


# Backward-compatible alias
CanonicalStory = CanonicalRequirement


class SDDSpecificationSeed(BaseModel):
    """A traceable seed, deliberately not the formal downstream SDD specification."""

    model_config = ConfigDict(extra="forbid")

    promotion_id: str = Field(default_factory=new_id)
    requirement_id: str
    requirement_version: int
    source_context_id: str
    source_context_version: int
    external_references: list[ExternalReference] = Field(default_factory=list)
    product_requirements: dict[str, Any]
    acceptance_criteria: list[AcceptanceCriterion]
    assumptions: list[str]
    dependencies: list[str]
    open_questions: list[str]
    ambiguity_flags: list[str]
    human_approval: dict[str, Any]
    ai_provenance: dict[str, Any]
    engineering_decisions: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="before")
    @classmethod
    def _handle_seed_legacy_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        if "story_id" in data and "requirement_id" not in data:
            data["requirement_id"] = data.pop("story_id")
        if "story_version" in data and "requirement_version" not in data:
            data["requirement_version"] = data.pop("story_version")

        jira_project = data.pop("jira_project_key", None)
        jira_key = data.pop("jira_issue_key", None)
        jira_url = data.pop("jira_issue_url", None)
        if any([jira_project, jira_key, jira_url]):
            refs = list(data.get("external_references") or [])
            refs.append(
                ExternalReference(
                    external_system="jira",
                    external_project=jira_project,
                    external_key=jira_key,
                    external_url=jira_url,
                )
            )
            data["external_references"] = refs
        return data

    @property
    def story_id(self) -> str:
        return self.requirement_id

    @property
    def story_version(self) -> int:
        return self.requirement_version

    @property
    def jira_project_key(self) -> str | None:
        for ref in self.external_references:
            if ref.external_system == "jira":
                return ref.external_project
        return None

    @property
    def jira_issue_key(self) -> str | None:
        for ref in self.external_references:
            if ref.external_system == "jira":
                return ref.external_key
        return None

    @property
    def jira_issue_url(self) -> str | None:
        for ref in self.external_references:
            if ref.external_system == "jira":
                return ref.external_url
        return None


class RequirementEvent(BaseModel):
    """Auditable metadata only; business-context contents are deliberately excluded."""

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(default_factory=new_id)
    event_type: str
    context_id: str | None = None
    requirement_id: str | None = None
    requirement_version: int | None = None
    story_id: str | None = None
    story_version: int | None = None
    actor: str | None = None
    occurred_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _handle_event_legacy_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        req_id = data.get("requirement_id") or data.get("story_id")
        req_ver = data.get("requirement_version") or data.get("story_version")
        if req_id is not None:
            data["requirement_id"] = req_id
            data["story_id"] = req_id
        if req_ver is not None:
            data["requirement_version"] = req_ver
            data["story_version"] = req_ver
        return data
