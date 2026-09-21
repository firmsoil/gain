from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx
import pytest

from gain.errors import (
    InvalidLifecycleTransitionError,
    JiraAuthenticationError,
    JiraIntegrationError,
    RequirementValidationError,
)
from gain.requirements.generation import StaticStoryProvider
from gain.requirements.jira import (
    JiraAdapter,
    JiraDescriptionFormat,
    JiraFieldConfiguration,
    JiraStoryMapper,
    JiraSynchronizationService,
)
from gain.requirements.models import (
    BusinessContext,
    CanonicalRequirement,
    CanonicalStory,
    ExternalReference,
    IssueType,
    StoryLifecycleStatus,
)
from gain.requirements.service import RequirementsService
from gain.requirements.storage import RequirementsStore, SpecificationSeedStore


def _context() -> BusinessContext:
    return BusinessContext(
        title="Reduce stale pull-request reviews",
        business_problem="Reviewers do not have a consistent way to identify stale pull requests.",
        business_goal="Give engineering managers an observable stale-review queue.",
        business_context="The platform team has already agreed the queue is needed.",
        stakeholders=["Engineering manager", "Platform team"],
        constraints=["Do not rank individual developers"],
        sources=["BA workshop 2026-09-13"],
    )


def _draft(project_key: str | None = "GAIN") -> dict[str, Any]:
    return {
        "project_key": project_key,
        "issue_type": "Story",
        "summary": "Show stale pull requests for review",
        "description": (
            "Expose a queue of pull requests awaiting review beyond the agreed threshold."
        ),
        "priority": "High",
        "labels": ["flow", "review"],
        "components": ["Analytics"],
        "role": "engineering manager",
        "capability": "view pull requests awaiting review",
        "business_value": "I can coordinate review work before requests become stale",
        "preconditions": ["Pull request data has been collected"],
        "assumptions": ["The stale threshold is configured by a human"],
        "dependencies": ["Canonical pull request dataset"],
        "risks": ["A stale label may be interpreted as individual performance data"],
        "acceptance_criteria": [
            {
                "summary": "A manager can find stale pull requests",
                "given": "a pull request has waited longer than the configured review threshold",
                "when": "the engineering manager views the stale-review queue",
                "then": "the pull request is included with its repository and waiting duration",
            }
        ],
    }


def _service(tmp_path: Path) -> RequirementsService:
    return RequirementsService(
        RequirementsStore(tmp_path / "requirements"),
        seed_store=SpecificationSeedStore(tmp_path / "seeds"),
    )


def _generated_service_story(
    tmp_path: Path,
) -> tuple[RequirementsService, BusinessContext, CanonicalStory]:
    service = _service(tmp_path)
    context = service.create_context(_context(), actor="ba@example.test")
    story = service.generate_story(
        context.context_id, StaticStoryProvider(_draft()), actor="ba@example.test"
    )
    return service, context, story


def test_generation_records_provenance_and_keeps_draft_non_authoritative(tmp_path: Path) -> None:
    service, context, story = _generated_service_story(tmp_path)

    assert story.lifecycle_status == StoryLifecycleStatus.DRAFT
    assert not story.is_authoritative_requirement
    assert story.source_context_id == context.context_id
    assert story.source_context_version == 1
    assert story.model_provider == "static-json"
    assert story.prompt_template_version == "story-generation-v1"
    assert story.input_hash and story.output_hash and story.generation_id
    assert story.acceptance_criteria[0].given
    assert service.store.story_history(story.story_id) == [story]


def test_business_context_changes_are_versioned_before_regeneration(tmp_path: Path) -> None:
    service = _service(tmp_path)
    original = service.create_context(_context(), actor="ba@example.test")

    revised = service.revise_context(
        original.context_id,
        {"constraints": ["Do not rank individual developers", "Use aggregated views"]},
        actor="ba@example.test",
    )

    assert revised.version == 2
    assert service.store.get_context(original.context_id, 1).constraints == [
        "Do not rank individual developers"
    ]
    assert service.store.get_context(original.context_id).version == 2


def test_malformed_provider_output_is_rejected_by_the_structured_contract(tmp_path: Path) -> None:
    service = _service(tmp_path)
    context = service.create_context(_context())

    with pytest.raises(RequirementValidationError, match="invalid structured draft"):
        service.generate_story(
            context.context_id, StaticStoryProvider({"issue_type": "Not a Jira type"})
        )


def test_human_revision_approval_and_promotion_preserve_prior_versions(tmp_path: Path) -> None:
    service, context, original = _generated_service_story(tmp_path)

    with pytest.raises(RequirementValidationError, match="approved"):
        service.promote_story(original.story_id)

    approved = service.approve_story(original.story_id, "ba@example.test")
    assert approved.version == 2
    assert approved.lifecycle_status == StoryLifecycleStatus.APPROVED
    assert approved.approved_by == "ba@example.test"
    seed = service.promote_story(approved.story_id)
    assert seed.story_id == approved.story_id
    assert seed.story_version == approved.version
    assert seed.source_context_id == context.context_id
    assert seed.engineering_decisions == []
    assert seed.human_approval["approved_by"] == "ba@example.test"

    revised = service.revise_story(
        approved.story_id,
        {"business_value": "I can unblock review work before it becomes stale"},
        reviewer="ba@example.test",
    )
    history = service.store.story_history(approved.story_id)
    assert revised.version == 3
    assert revised.lifecycle_status == StoryLifecycleStatus.DRAFT
    assert [version.lifecycle_status for version in history] == [
        StoryLifecycleStatus.DRAFT,
        StoryLifecycleStatus.APPROVED,
        StoryLifecycleStatus.DRAFT,
    ]
    assert history[0].business_value != revised.business_value


def test_only_approved_stories_can_be_exported_or_linked_to_a_formal_specification(
    tmp_path: Path,
) -> None:
    service, _, draft = _generated_service_story(tmp_path)
    mapper = JiraStoryMapper()
    with pytest.raises(RequirementValidationError, match="story_not_approved"):
        mapper.to_payload(draft)
    with pytest.raises(InvalidLifecycleTransitionError, match="approved"):
        service.link_formal_specification(
            draft.story_id, "specs/003-example", actor="ba@example.test"
        )

    approved = service.approve_story(draft.story_id, "ba@example.test")
    linked = service.link_formal_specification(
        approved.story_id,
        "specs/003-example",
        actor="architect@example.test",
    )
    assert linked.lifecycle_status == StoryLifecycleStatus.APPROVED
    assert linked.parent_spec_id == "specs/003-example"
    assert linked.version == approved.version + 1


def test_regeneration_preserves_the_original_draft_and_requires_fresh_review(
    tmp_path: Path,
) -> None:
    service, _, original = _generated_service_story(tmp_path)
    service.request_review(original.story_id, "ba@example.test")
    regenerated_payload = _draft()
    regenerated_payload["summary"] = "Regenerated stale review queue"

    regenerated = service.regenerate_story(
        original.story_id,
        StaticStoryProvider(regenerated_payload),
        actor="ba@example.test",
    )

    history = service.store.story_history(original.story_id)
    assert regenerated.version == 3
    assert regenerated.lifecycle_status == StoryLifecycleStatus.DRAFT
    assert regenerated.summary == "Regenerated stale review queue"
    assert history[0].summary != regenerated.summary
    assert history[1].lifecycle_status == StoryLifecycleStatus.IN_REVIEW


def test_approval_requires_complete_gherkin_and_resolved_material_questions(tmp_path: Path) -> None:
    service = _service(tmp_path)
    context = service.create_context(_context())
    invalid = _draft()
    invalid["open_questions"] = ["Which elapsed duration should be stale?"]
    invalid["acceptance_criteria"] = [
        {"given": "a request exists", "when": "it is viewed", "then": ""}
    ]
    story = service.generate_story(context.context_id, StaticStoryProvider(invalid))

    report = service.validate_story(story)
    assert {issue.code for issue in report.errors} >= {
        "malformed_given_when_then",
        "unresolved_open_questions",
    }
    with pytest.raises(RequirementValidationError, match="malformed_given_when_then"):
        service.approve_story(story.story_id, "ba@example.test")


def test_jira_mapping_uses_adf_custom_fields_and_omits_unknown_optional_data(
    tmp_path: Path,
) -> None:
    service, _, draft = _generated_service_story(tmp_path)
    revised = service.revise_story(
        draft.story_id,
        {"story_points": 3, "sprint": "42", "reporter": None, "assignee": None},
        reviewer="ba@example.test",
    )
    approved = service.approve_story(revised.story_id, "ba@example.test")
    mapper = JiraStoryMapper(
        JiraFieldConfiguration(
            description_format=JiraDescriptionFormat.ADF,
            story_points_field_id="customfield_10016",
            sprint_field_id="customfield_10020",
            allowed_priorities={"High", "Medium", "Low"},
        )
    )

    payload = mapper.to_payload(approved)
    fields = payload["fields"]
    assert fields["project"] == {"key": "GAIN"}
    assert fields["issuetype"] == {"name": "Story"}
    assert fields["customfield_10016"] == 3
    assert fields["customfield_10020"] == "42"
    assert fields["description"]["type"] == "doc"
    assert "assignee" not in fields and "reporter" not in fields
    adf_text = " ".join(str(node) for node in fields["description"]["content"])
    assert "Given" in adf_text and "Then" in adf_text

    wiki_payload = JiraStoryMapper(
        JiraFieldConfiguration(
            description_format=JiraDescriptionFormat.WIKI,
            story_points_field_id="customfield_10016",
            sprint_field_id="customfield_10020",
        )
    ).to_payload(approved)
    assert "h2. Acceptance Criteria" in wiki_payload["fields"]["description"]


def test_jira_project_can_be_derived_only_from_explicit_configuration(tmp_path: Path) -> None:
    service, _, draft = _generated_service_story(tmp_path)
    draft_without_project = service.revise_story(
        draft.story_id,
        {"project_key": None},
        reviewer="ba@example.test",
    )
    approved = service.approve_story(draft_without_project.story_id, "ba@example.test")

    payload = JiraStoryMapper(JiraFieldConfiguration(default_project_key="PLATFORM")).to_payload(
        approved
    )
    assert payload["fields"]["project"] == {"key": "PLATFORM"}


def test_jira_reverse_mapping_keeps_imported_issue_non_authoritative() -> None:
    mapper = JiraStoryMapper(JiraFieldConfiguration(description_format=JiraDescriptionFormat.ADF))
    imported = mapper.from_jira_issue(
        {
            "id": "10900",
            "key": "GAIN-21",
            "self": "https://jira.example.test/rest/api/3/issue/10900",
            "fields": {
                "project": {"key": "GAIN"},
                "issuetype": {"name": "Story"},
                "summary": "Imported issue",
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": "Imported description"}],
                        }
                    ],
                },
                "priority": {"name": "Medium"},
                "labels": ["imported"],
                "components": [{"name": "Analytics"}],
                "updated": "2026-09-13T00:00:00.000+0000",
            },
        },
        source_context_id="context-1",
    )
    assert imported.issue_type == IssueType.STORY
    assert imported.external_issue_id == "10900"
    assert imported.external_issue_key == "GAIN-21"
    assert imported.description == "Imported description"
    assert imported.lifecycle_status == StoryLifecycleStatus.DRAFT
    assert not imported.is_authoritative_requirement
    assert imported.role == ""


class _FakeJiraAdapter:
    def __init__(self) -> None:
        self.create_calls = 0
        self.update_calls = 0

    def find_story_by_external_reference(self, story_id: str) -> Mapping[str, Any] | None:
        del story_id
        return None

    def create_story(
        self, payload: Mapping[str, Any], external_reference: str
    ) -> Mapping[str, Any]:
        assert payload["fields"]["summary"]
        assert external_reference
        self.create_calls += 1
        return {"id": "10101", "key": "GAIN-101", "self": "https://jira.example.test/GAIN-101"}

    def update_story(self, issue_id_or_key: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        assert issue_id_or_key == "10101"
        assert payload["fields"]["summary"]
        self.update_calls += 1
        return {
            "id": "10101",
            "key": "GAIN-101",
            "self": "https://jira.example.test/GAIN-101",
            "fields": {"updated": "2026-09-13T01:00:00.000+0000"},
        }

    def get_story(self, issue_id_or_key: str) -> Mapping[str, Any]:
        del issue_id_or_key
        raise AssertionError("not used by synchronization service")

    def transition_story(self, issue_id_or_key: str, transition_id: str) -> None:
        del issue_id_or_key, transition_id


def test_jira_sync_persists_external_identity_and_prevents_repeat_create(tmp_path: Path) -> None:
    service, _, draft = _generated_service_story(tmp_path)
    approved = service.approve_story(draft.story_id, "ba@example.test")
    adapter = _FakeJiraAdapter()
    sync = JiraSynchronizationService(JiraStoryMapper(), service.store)

    created = sync.synchronize(approved, adapter)
    updated = sync.synchronize(created, adapter)

    assert created.external_issue_id == "10101"
    assert created.external_issue_key == "GAIN-101"
    assert created.version == 3
    assert updated.version == 4
    assert adapter.create_calls == 1
    assert adapter.update_calls == 1
    assert service.store.get_story(draft.story_id).external_issue_key == "GAIN-101"


def test_jira_authentication_failure_is_safe_and_typed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-token"
        return httpx.Response(401, text="unauthorized")

    adapter = JiraAdapter(
        "https://jira.example.test",
        "test-token",
        max_retries=0,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(JiraAuthenticationError, match="status 401"):
        adapter.get_story("GAIN-1")


def test_jira_adapter_retries_rate_limits_and_rejects_malformed_responses() -> None:
    calls = 0

    def retry_handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"retry-after": "0"})
        return httpx.Response(200, json={"id": "10001", "key": "GAIN-1"})

    adapter = JiraAdapter(
        "https://jira.example.test",
        "test-token",
        max_retries=1,
        base_backoff_seconds=0,
        transport=httpx.MockTransport(retry_handler),
    )
    assert adapter.get_story("GAIN-1")["key"] == "GAIN-1"
    assert calls == 2

    malformed = JiraAdapter(
        "https://jira.example.test",
        "test-token",
        max_retries=0,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, text="not-json")),
    )
    with pytest.raises(JiraIntegrationError, match="malformed"):
        malformed.get_story("GAIN-1")


def test_canonical_requirement_has_independent_identity_and_story_semantics(
    tmp_path: Path,
) -> None:
    service, context, story = _generated_service_story(tmp_path)

    # Stable independent identity
    assert story.requirement_id
    assert story.story_id == story.requirement_id
    assert story.version == 1

    # Story semantics stored separately
    assert story.role == "engineering manager"
    assert story.capability == "view pull requests awaiting review"
    assert story.business_value == "I can coordinate review work before requests become stale"

    # Acceptance criteria are structured first-class domain objects
    assert len(story.acceptance_criteria) == 1
    ac = story.acceptance_criteria[0]
    assert ac.criterion_id
    assert ac.given.startswith("a pull request has waited")
    assert ac.when == "the engineering manager views the stale-review queue"
    assert ac.then.startswith("the pull request is included")


def test_adapter_isolation_domain_modules_do_not_import_jira_or_httpx() -> None:
    import importlib
    import sys

    domain_modules = [
        "gain.requirements.models",
        "gain.requirements.generation",
        "gain.requirements.quality",
        "gain.requirements.sdd",
        "gain.requirements.storage",
    ]
    for mod_name in domain_modules:
        mod = sys.modules.get(mod_name) or importlib.import_module(mod_name)
        assert not hasattr(mod, "JiraAdapter")
        assert not hasattr(mod, "JiraStoryMapper")
        assert not hasattr(mod, "httpx")


def test_sdd_promotion_pure_git_workflow_without_jira(tmp_path: Path) -> None:
    service = _service(tmp_path)
    context = service.create_context(_context(), actor="ba@example.test")

    # Draft with zero Jira fields or references
    pure_draft = _draft(project_key=None)
    pure_draft.pop("project_key", None)
    pure_draft.pop("issue_type", None)

    requirement = service.generate_story(
        context.context_id, StaticStoryProvider(pure_draft), actor="ba@example.test"
    )
    approved = service.approve_story(requirement.requirement_id, reviewer="lead@example.test")

    # Promotion to SDD succeeds with ZERO Jira configuration or references
    seed = service.promote_story(approved.requirement_id)
    assert seed.requirement_id == approved.requirement_id
    assert seed.story_id == approved.requirement_id
    assert seed.requirement_version == approved.version
    assert seed.source_context_id == context.context_id
    assert seed.external_references == []
    assert seed.jira_issue_key is None
    assert seed.jira_project_key is None
    assert len(seed.acceptance_criteria) == 1
    assert seed.human_approval["approved_by"] == "lead@example.test"


def test_end_to_end_requirement_lifecycle_to_jira_and_sdd(tmp_path: Path) -> None:
    # 1. Business Context
    service = _service(tmp_path)
    context = service.create_context(_context(), actor="ba@example.test")
    assert context.version == 1

    # 2. AI Draft Generation (non-authoritative)
    draft = service.generate_story(
        context.context_id, StaticStoryProvider(_draft()), actor="ba@example.test"
    )
    assert draft.lifecycle_status == StoryLifecycleStatus.DRAFT
    assert not draft.is_authoritative_requirement

    # 3. Human Review & Revision
    revised = service.revise_story(
        draft.requirement_id,
        {
            "business_value": "I can proactively rebalance reviewer workload",
            "assumptions": ["Review SLA is 48 hours"],
        },
        reviewer="ba@example.test",
    )
    assert revised.version == 2
    assert revised.assumptions == ["Review SLA is 48 hours"]

    # 4. Human Approval
    approved = service.approve_story(revised.requirement_id, reviewer="manager@example.test")
    assert approved.version == 3
    assert approved.lifecycle_status == StoryLifecycleStatus.APPROVED
    assert approved.is_authoritative_requirement

    # 5. Jira Projection (Deterministic Adapter)
    adapter = _FakeJiraAdapter()
    sync = JiraSynchronizationService(JiraStoryMapper(), service.store)
    synced = sync.synchronize(approved, adapter)
    assert synced.version == 4
    assert synced.external_issue_key == "GAIN-101"
    assert synced.get_external_reference("jira") is not None

    # 6. SDD Promotion
    seed = service.promote_story(synced.requirement_id)
    assert seed.requirement_id == synced.requirement_id
    assert seed.jira_issue_key == "GAIN-101"
    assert seed.product_requirements["business_value"] == (
        "I can proactively rebalance reviewer workload"
    )

    # 7. Link to Formal SDD Specification
    linked = service.link_formal_specification(
        synced.requirement_id, "specs/004-stale-reviews", actor="architect@example.test"
    )
    assert linked.parent_spec_id == "specs/004-stale-reviews"
    assert linked.version == 5


def test_jira_failures_do_not_corrupt_or_invalidate_canonical_requirement(tmp_path: Path) -> None:
    service, _, draft = _generated_service_story(tmp_path)
    approved = service.approve_story(draft.story_id, "ba@example.test")

    # Jira failure due to auth error
    def auth_error_handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized")

    failing_adapter = JiraAdapter(
        "https://jira.example.test",
        "bad-token",
        max_retries=0,
        transport=httpx.MockTransport(auth_error_handler),
    )
    sync = JiraSynchronizationService(JiraStoryMapper(), service.store)

    with pytest.raises(JiraAuthenticationError):
        sync.synchronize(approved, failing_adapter)

    # The canonical requirement remains APPROVED and uncorrupted!
    stored = service.store.get_story(approved.story_id)
    assert stored.lifecycle_status == StoryLifecycleStatus.APPROVED
    assert stored.version == approved.version
    assert stored.is_authoritative_requirement


def test_external_reference_preserves_multisystem_identities() -> None:
    req = CanonicalRequirement(
        source_context_id="ctx-1",
        source_context_version=1,
        summary="Support multi-system traceability",
        external_references=[
            ExternalReference(
                external_system="jira",
                external_project="GAIN",
                external_key="GAIN-200",
                external_id="20000",
                external_url="https://jira.example.test/browse/GAIN-200",
            ),
            ExternalReference(
                external_system="github",
                external_project="org/repo",
                external_key="#42",
                external_id="987654",
                external_url="https://github.com/org/repo/issues/42",
            ),
        ],
    )
    assert req.external_issue_key == "GAIN-200"
    assert req.get_external_reference("jira") is not None
    assert req.get_external_reference("github") is not None
    assert req.get_external_reference("github").external_key == "#42"  # type: ignore[union-attr]
