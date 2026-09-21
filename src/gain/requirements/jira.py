from __future__ import annotations

import time
from collections.abc import Mapping
from contextlib import suppress
from enum import StrEnum
from typing import Any, Protocol

import httpx
import structlog
from pydantic import BaseModel, ConfigDict, Field

from gain.errors import JiraAuthenticationError, JiraIntegrationError, RequirementValidationError
from gain.requirements.models import (
    CanonicalRequirement,
    CanonicalStory,
    ExternalReference,
    IssueType,
    RequirementEvent,
    RequirementLifecycleStatus,
    RequirementType,
    StoryLifecycleStatus,
    new_id,
    utc_now,
)
from gain.requirements.quality import (
    IssueSeverity,
    StoryQualityIssue,
    StoryQualityReport,
    validate_story_quality,
)
from gain.requirements.storage import RequirementsStore

log = structlog.get_logger(__name__)


class JiraDescriptionFormat(StrEnum):
    WIKI = "wiki"
    ADF = "adf"


class JiraFieldConfiguration(BaseModel):
    """Instance-specific choices; Jira custom-field IDs never enter the domain model."""

    model_config = ConfigDict(extra="forbid")

    description_format: JiraDescriptionFormat = JiraDescriptionFormat.ADF
    default_project_key: str | None = None
    story_points_field_id: str | None = None
    sprint_field_id: str | None = None
    # Jira Cloud commonly requires accountId; deployments can select another supported identifier.
    user_identifier_field: str = "accountId"
    allowed_issue_types: set[IssueType] = Field(default_factory=lambda: set(IssueType))
    allowed_priorities: set[str] = Field(default_factory=set)
    allowed_labels: set[str] = Field(default_factory=set)
    allowed_components: set[str] = Field(default_factory=set)
    require_priority: bool = False


def _jira_name(value: str) -> dict[str, str]:
    return {"name": value}


def _bullet(lines: list[str]) -> str:
    return "\n".join(f"* {line}" for line in lines)


def render_wiki_description(story: CanonicalStory) -> str:
    sections = [
        "h2. User Story",
        f"As a {story.role},\nI want {story.capability},\nso that {story.business_value}.",
        "h2. Description",
        story.description,
    ]
    if story.preconditions:
        sections.extend(["h2. Preconditions", _bullet(story.preconditions)])
    if story.source_context_id:
        sections.extend(["h2. Business Context", f"GAIN context: {story.source_context_id}"])
    acceptance = []
    for criterion in story.acceptance_criteria:
        acceptance.extend(
            [
                f"Given {criterion.given}",
                *(f"And {part}" for part in criterion.and_given),
                f"When {criterion.when}",
                *(f"And {part}" for part in criterion.and_when),
                f"Then {criterion.then}",
                *(f"And {part}" for part in criterion.and_then),
            ]
        )
    if acceptance:
        sections.extend(["h2. Acceptance Criteria", _bullet(acceptance)])
    for title, values in (
        ("Assumptions", story.assumptions),
        ("Dependencies", story.dependencies),
        ("Risks", story.risks),
        ("Open Questions", story.open_questions),
    ):
        if values:
            sections.extend([f"h2. {title}", _bullet(values)])
    return "\n\n".join(section for section in sections if section.strip())


def _paragraph(text: str) -> dict[str, Any]:
    return {"type": "paragraph", "content": [{"type": "text", "text": text}]}


def _heading(text: str) -> dict[str, Any]:
    return {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": text}]}


def _bullet_list(lines: list[str]) -> dict[str, Any]:
    return {
        "type": "bulletList",
        "content": [
            {"type": "listItem", "content": [_paragraph(line)]} for line in lines if line.strip()
        ],
    }


def render_adf_description(story: CanonicalStory) -> dict[str, Any]:
    content: list[dict[str, Any]] = [
        _heading("User Story"),
        _paragraph(
            f"As a {story.role}, I want {story.capability}, so that {story.business_value}."
        ),
        _heading("Description"),
        _paragraph(story.description),
    ]
    if story.preconditions:
        content.extend([_heading("Preconditions"), _bullet_list(story.preconditions)])
    content.extend(
        [_heading("Business Context"), _paragraph(f"GAIN context: {story.source_context_id}")]
    )
    acceptance: list[str] = []
    for criterion in story.acceptance_criteria:
        acceptance.extend(
            [
                f"Given {criterion.given}",
                *(f"And {part}" for part in criterion.and_given),
                f"When {criterion.when}",
                *(f"And {part}" for part in criterion.and_when),
                f"Then {criterion.then}",
                *(f"And {part}" for part in criterion.and_then),
            ]
        )
    if acceptance:
        content.extend([_heading("Acceptance Criteria"), _bullet_list(acceptance)])
    for title, values in (
        ("Assumptions", story.assumptions),
        ("Dependencies", story.dependencies),
        ("Risks", story.risks),
        ("Open Questions", story.open_questions),
    ):
        if values:
            content.extend([_heading(title), _bullet_list(values)])
    return {"type": "doc", "version": 1, "content": content}


def _adf_to_text(node: Any) -> str:
    if isinstance(node, str):
        return node
    if not isinstance(node, Mapping):
        return ""
    own = str(node.get("text") or "")
    child_text = "\n".join(_adf_to_text(child) for child in node.get("content", [])).strip()
    return "\n".join(part for part in (own, child_text) if part)


def _read_named(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        for key in ("name", "key", "displayName", "accountId", "value"):
            item = value.get(key)
            if item is not None:
                return str(item)
    return None


class JiraStoryMapper:
    def __init__(self, configuration: JiraFieldConfiguration | None = None) -> None:
        self.configuration = configuration or JiraFieldConfiguration()

    def validate_for_export(self, story: CanonicalStory) -> StoryQualityReport:
        issues = list(validate_story_quality(story).issues)
        config = self.configuration
        if story.lifecycle_status != StoryLifecycleStatus.APPROVED:
            issues.append(
                StoryQualityIssue(
                    "story_not_approved",
                    IssueSeverity.ERROR,
                    "Only a human-approved story can be exported to Jira",
                )
            )
        if not (story.project_key or config.default_project_key):
            issues.append(
                StoryQualityIssue(
                    "missing_project_key",
                    IssueSeverity.ERROR,
                    "project_key is required for Jira export",
                )
            )
        if story.issue_type not in config.allowed_issue_types:
            issues.append(
                StoryQualityIssue(
                    "invalid_issue_type",
                    IssueSeverity.ERROR,
                    "Issue type is not allowed by Jira configuration",
                )
            )
        if config.require_priority and not story.priority:
            issues.append(
                StoryQualityIssue(
                    "missing_priority",
                    IssueSeverity.ERROR,
                    "Priority is required by Jira configuration",
                )
            )
        if (
            story.priority
            and config.allowed_priorities
            and story.priority not in config.allowed_priorities
        ):
            issues.append(
                StoryQualityIssue(
                    "invalid_priority",
                    IssueSeverity.ERROR,
                    "Priority is not allowed by Jira configuration",
                )
            )
        if story.story_points is not None and not config.story_points_field_id:
            issues.append(
                StoryQualityIssue(
                    "missing_story_points_field",
                    IssueSeverity.ERROR,
                    "Story points field ID is not configured",
                )
            )
        if story.sprint and not config.sprint_field_id:
            issues.append(
                StoryQualityIssue(
                    "missing_sprint_field", IssueSeverity.ERROR, "Sprint field ID is not configured"
                )
            )
        if config.allowed_labels and set(story.labels) - config.allowed_labels:
            issues.append(
                StoryQualityIssue(
                    "invalid_labels", IssueSeverity.ERROR, "One or more labels are not allowed"
                )
            )
        if config.allowed_components and set(story.components) - config.allowed_components:
            issues.append(
                StoryQualityIssue(
                    "invalid_components",
                    IssueSeverity.ERROR,
                    "One or more components are not allowed",
                )
            )
        if story.parent_key and story.epic_key and story.parent_key != story.epic_key:
            issues.append(
                StoryQualityIssue(
                    "inconsistent_parent_epic",
                    IssueSeverity.ERROR,
                    "parent_key and epic_key conflict",
                )
            )
        if story.parent_id and story.epic_id and story.parent_id != story.epic_id:
            issues.append(
                StoryQualityIssue(
                    "inconsistent_parent_epic",
                    IssueSeverity.ERROR,
                    "parent_id and epic_id conflict",
                )
            )
        if story.issue_type == IssueType.EPIC and (story.parent_key or story.epic_key):
            issues.append(
                StoryQualityIssue(
                    "epic_parent_invalid", IssueSeverity.ERROR, "An Epic cannot be its own child"
                )
            )
        return StoryQualityReport(tuple(issues))

    def to_payload(self, story: CanonicalStory) -> dict[str, Any]:
        report = self.validate_for_export(story)
        if not report.is_valid:
            raise RequirementValidationError(
                "Story cannot be exported to Jira: "
                + "; ".join(issue.code for issue in report.errors)
            )
        config = self.configuration
        description: str | dict[str, Any]
        if config.description_format == JiraDescriptionFormat.ADF:
            description = render_adf_description(story)
        else:
            description = render_wiki_description(story)
        project_key = story.project_key or config.default_project_key
        assert project_key is not None
        fields: dict[str, Any] = {
            "project": {"key": project_key},
            "issuetype": _jira_name(story.issue_type.value),
            "summary": story.summary,
            "description": description,
        }
        if story.priority:
            fields["priority"] = _jira_name(story.priority)
        if story.assignee:
            fields["assignee"] = {config.user_identifier_field: story.assignee}
        if story.reporter:
            fields["reporter"] = {config.user_identifier_field: story.reporter}
        if story.labels:
            fields["labels"] = story.labels
        if story.components:
            fields["components"] = [_jira_name(component) for component in story.components]
        parent_key = story.parent_key or story.epic_key
        parent_id = story.parent_id or story.epic_id
        if parent_key:
            fields["parent"] = {"key": parent_key}
        elif parent_id:
            fields["parent"] = {"id": parent_id}
        if story.fix_versions:
            fields["fixVersions"] = [_jira_name(value) for value in story.fix_versions]
        if story.affects_versions:
            fields["versions"] = [_jira_name(value) for value in story.affects_versions]
        if story.story_points is not None:
            assert config.story_points_field_id is not None
            fields[config.story_points_field_id] = story.story_points
        if story.sprint:
            assert config.sprint_field_id is not None
            fields[config.sprint_field_id] = story.sprint
        return {"fields": fields}

    def from_jira_issue(
        self,
        issue: Mapping[str, Any],
        *,
        source_context_id: str,
        source_context_version: int = 1,
    ) -> CanonicalStory:
        fields = issue.get("fields")
        if not isinstance(fields, Mapping):
            fields = issue
        raw_description = fields.get("description") or ""
        description = (
            _adf_to_text(raw_description)
            if isinstance(raw_description, Mapping)
            else str(raw_description)
        )
        project_value = fields.get("project")
        project_key = _read_named(project_value)
        issue_type = _read_named(fields.get("issuetype")) or IssueType.STORY.value
        labels = [str(value) for value in fields.get("labels") or []]
        components = [
            value
            for value in (_read_named(item) for item in fields.get("components") or [])
            if value
        ]
        fix_versions = [
            value
            for value in (_read_named(item) for item in fields.get("fixVersions") or [])
            if value
        ]
        affects_versions = [
            value for value in (_read_named(item) for item in fields.get("versions") or []) if value
        ]
        parent = fields.get("parent")
        parent_key = _read_named(parent)
        config = self.configuration
        story_points: float | None = None
        if config.story_points_field_id and fields.get(config.story_points_field_id) is not None:
            story_points = float(fields[config.story_points_field_id])
        sprint: str | None = None
        if config.sprint_field_id and fields.get(config.sprint_field_id) is not None:
            sprint = str(fields[config.sprint_field_id])
        jira_ref = ExternalReference(
            external_system="jira",
            external_project=project_key,
            external_type=issue_type,
            external_id=str(issue.get("id")) if issue.get("id") is not None else None,
            external_key=str(issue.get("key")) if issue.get("key") is not None else None,
            external_url=str(issue.get("self")) if issue.get("self") is not None else None,
            external_version=str(fields.get("updated")) if fields.get("updated") else None,
            last_synced_at=utc_now(),
        )
        custom_fields: dict[str, Any] = {}
        if project_key:
            custom_fields["project_key"] = project_key
        if story_points is not None:
            custom_fields["story_points"] = story_points
        if sprint:
            custom_fields["sprint"] = sprint
        if parent_key:
            custom_fields["parent_key"] = parent_key
        if parent and isinstance(parent, Mapping) and parent.get("id"):
            custom_fields["parent_id"] = str(parent.get("id"))
        if fix_versions:
            custom_fields["fix_versions"] = fix_versions
        if affects_versions:
            custom_fields["affects_versions"] = affects_versions
        reporter = _read_named(fields.get("reporter"))
        if reporter:
            custom_fields["reporter"] = reporter
        assignee = _read_named(fields.get("assignee"))
        if assignee:
            custom_fields["assignee"] = assignee
        status = _read_named(fields.get("status"))
        if status:
            custom_fields["status"] = status

        req_type = RequirementType.STORY
        if issue_type in RequirementType._value2member_map_:
            req_type = RequirementType(issue_type)

        return CanonicalRequirement(
            requirement_id=new_id(),
            version=1,
            lifecycle_status=RequirementLifecycleStatus.DRAFT,
            source_context_id=source_context_id,
            source_context_version=source_context_version,
            requirement_type=req_type,
            summary=str(fields.get("summary") or ""),
            description=description,
            priority=_read_named(fields.get("priority")),
            labels=labels,
            components=components,
            external_references=[jira_ref],
            custom_fields=custom_fields,
            created_at=utc_now(),
            updated_at=utc_now(),
        )


class IssueTrackerAdapter(Protocol):
    def find_story_by_external_reference(self, story_id: str) -> Mapping[str, Any] | None: ...

    def create_story(
        self, payload: Mapping[str, Any], external_reference: str
    ) -> Mapping[str, Any]: ...

    def update_story(
        self, issue_id_or_key: str, payload: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...

    def get_story(self, issue_id_or_key: str) -> Mapping[str, Any]: ...

    def transition_story(self, issue_id_or_key: str, transition_id: str) -> None: ...


class JiraAdapter:
    """Jira Cloud REST adapter. Tokens are retained only in headers and never logged."""

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        base_backoff_seconds: float = 1.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.base_backoff_seconds = base_backoff_seconds
        self.transport = transport

    def _request(
        self, method: str, path: str, *, json_body: Mapping[str, Any] | None = None
    ) -> Mapping[str, Any]:
        for attempt in range(self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout_seconds, transport=self.transport) as client:
                    response = client.request(
                        method, f"{self.base_url}{path}", headers=self._headers, json=json_body
                    )
            except (httpx.NetworkError, httpx.TimeoutException) as exc:
                if attempt >= self.max_retries:
                    raise JiraIntegrationError("Jira network request failed after retries") from exc
                self._wait(attempt)
                continue
            if response.status_code in {401, 403}:
                raise JiraAuthenticationError(
                    f"Jira authentication or authorization failed (status {response.status_code})"
                )
            if response.status_code == 429 or 500 <= response.status_code < 600:
                if attempt >= self.max_retries:
                    raise JiraIntegrationError(
                        f"Jira service unavailable after retries (status {response.status_code})"
                    )
                self._wait(attempt, response.headers.get("retry-after"))
                continue
            if response.status_code >= 400:
                raise JiraIntegrationError(f"Jira request failed (status {response.status_code})")
            if not response.content:
                return {}
            try:
                payload = response.json()
            except ValueError as exc:
                raise JiraIntegrationError("Jira returned a malformed response") from exc
            if not isinstance(payload, Mapping):
                raise JiraIntegrationError("Jira returned an unexpected response shape")
            return payload
        raise AssertionError("unreachable")

    def _wait(self, attempt: int, retry_after: str | None = None) -> None:
        delay = self.base_backoff_seconds * (2**attempt)
        if retry_after:
            with suppress(ValueError):
                delay = min(delay, float(retry_after))
        log.warning("jira_retry", attempt=attempt, delay_seconds=delay)
        time.sleep(delay)

    def find_story_by_external_reference(self, story_id: str) -> Mapping[str, Any] | None:
        # Jira has no universal external-reference field. Stable GAIN persistence prevents
        # duplicates in this thin slice; deployments can implement this with a Jira property.
        del story_id
        return None

    def create_story(
        self, payload: Mapping[str, Any], external_reference: str
    ) -> Mapping[str, Any]:
        del external_reference
        return self._request("POST", "/rest/api/3/issue", json_body=payload)

    def update_story(self, issue_id_or_key: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        self._request("PUT", f"/rest/api/3/issue/{issue_id_or_key}", json_body=payload)
        return self.get_story(issue_id_or_key)

    def get_story(self, issue_id_or_key: str) -> Mapping[str, Any]:
        return self._request("GET", f"/rest/api/3/issue/{issue_id_or_key}")

    def transition_story(self, issue_id_or_key: str, transition_id: str) -> None:
        self._request(
            "POST",
            f"/rest/api/3/issue/{issue_id_or_key}/transitions",
            json_body={"transition": {"id": transition_id}},
        )


class JiraSynchronizationService:
    """Synchronizes only approved stories and records a new immutable GAIN version."""

    def __init__(self, mapper: JiraStoryMapper, store: RequirementsStore | None = None) -> None:
        self.mapper = mapper
        self.store = store

    def synchronize(self, story: CanonicalStory, adapter: IssueTrackerAdapter) -> CanonicalStory:
        if story.lifecycle_status != StoryLifecycleStatus.APPROVED:
            raise RequirementValidationError("Only an approved story can be synchronized to Jira")
        payload = self.mapper.to_payload(story)
        issue: Mapping[str, Any]
        if story.external_issue_id or story.external_issue_key:
            issue = adapter.update_story(
                story.external_issue_id or story.external_issue_key or "", payload
            )
            action = "jira_updated"
        else:
            existing = adapter.find_story_by_external_reference(story.story_id)
            if existing is None:
                issue = adapter.create_story(payload, story.story_id)
                action = "jira_created"
            else:
                external_id = str(existing.get("id") or existing.get("key") or "")
                if not external_id:
                    raise JiraIntegrationError(
                        "Jira duplicate lookup returned no stable identifier"
                    )
                issue = adapter.update_story(external_id, payload)
                action = "jira_duplicate_resolved"
        raw_fields = issue.get("fields")
        fields: Mapping[str, Any] = raw_fields if isinstance(raw_fields, Mapping) else {}
        issue_id = str(issue.get("id")) if issue.get("id") is not None else story.external_issue_id
        issue_key = (
            str(issue.get("key")) if issue.get("key") is not None else story.external_issue_key
        )
        issue_url = str(issue.get("self")) if issue.get("self") is not None else story.external_url
        issue_ver = (
            str(fields.get("updated")) if fields.get("updated") else story.external_source_version
        )
        jira_ref = ExternalReference(
            external_system="jira",
            external_project=story.project_key or self.mapper.configuration.default_project_key,
            external_id=issue_id,
            external_key=issue_key,
            external_url=issue_url,
            external_version=issue_ver,
            last_synced_at=utc_now(),
        )
        updated_refs = [r for r in story.external_references if r.external_system != "jira"]
        updated_refs.append(jira_ref)

        updated = story.model_copy(
            update={
                "version": story.version + 1,
                "external_references": updated_refs,
                "updated_at": utc_now(),
                "revision_reason": action,
            }
        )
        if self.store:
            self.store.save_story(updated)
            self.store.append_event(
                RequirementEvent(
                    event_type=action,
                    requirement_id=updated.requirement_id,
                    requirement_version=updated.version,
                    metadata={"external_issue_key": updated.external_issue_key or ""},
                )
            )
        return updated


JiraRequirementMapper = JiraStoryMapper
