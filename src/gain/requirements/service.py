from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from gain.errors import InvalidLifecycleTransitionError, RequirementValidationError
from gain.requirements.generation import StoryGenerationProvider, StoryGenerationService
from gain.requirements.models import (
    BusinessContext,
    CanonicalRequirement,
    CanonicalStory,
    GeneratedRequirementDraft,
    RequirementEvent,
    RequirementLifecycleStatus,
    SDDSpecificationSeed,
    StoryLifecycleStatus,
    utc_now,
)
from gain.requirements.quality import StoryQualityReport, validate_story_quality
from gain.requirements.sdd import build_specification_seed
from gain.requirements.storage import RequirementsStore, SpecificationSeedStore


class RequirementsService:
    """Application service for the governed requirements lifecycle."""

    def __init__(
        self,
        store: RequirementsStore,
        *,
        seed_store: SpecificationSeedStore | None = None,
        generation_service: StoryGenerationService | None = None,
    ) -> None:
        self.store = store
        self.seed_store = seed_store
        self.generation_service = generation_service or StoryGenerationService()

    def create_context(self, context: BusinessContext, actor: str | None = None) -> BusinessContext:
        if context.version != 1:
            raise RequirementValidationError(
                "A newly created business context must start at version 1"
            )
        self.store.save_context(context)
        self.store.append_event(
            RequirementEvent(
                event_type="business_context_created", context_id=context.context_id, actor=actor
            )
        )
        return context

    def revise_context(
        self,
        context_id: str,
        changes: Mapping[str, Any],
        *,
        actor: str,
    ) -> BusinessContext:
        """Version BA-supplied context before it is used for a regenerated story."""

        current = self.store.get_context(context_id)
        immutable_fields = {"context_id", "version", "created_at", "updated_at"}
        unknown = set(changes) - set(BusinessContext.model_fields)
        immutable = set(changes) & immutable_fields
        if unknown or immutable:
            unsupported = sorted(unknown | immutable)
            raise RequirementValidationError(
                "Business context fields cannot be revised: " + ", ".join(unsupported)
            )
        data = current.model_dump()
        data.update(changes)
        data.update(version=current.version + 1, updated_at=utc_now())
        revised = BusinessContext.model_validate(data)
        self.store.save_context(revised)
        self.store.append_event(
            RequirementEvent(
                event_type="business_context_revised",
                context_id=revised.context_id,
                actor=actor,
                metadata={"context_version": str(revised.version)},
            )
        )
        return revised

    def generate_story(
        self,
        context_id: str,
        provider: StoryGenerationProvider,
        *,
        actor: str | None = None,
        generation_parameters: Mapping[str, Any] | None = None,
    ) -> CanonicalStory:
        context = self.store.get_context(context_id)
        self.store.append_event(
            RequirementEvent(
                event_type="story_generation_requested", context_id=context.context_id, actor=actor
            )
        )
        try:
            story = self.generation_service.generate(context, provider, generation_parameters)
        except Exception:
            self.store.append_event(
                RequirementEvent(
                    event_type="story_generation_failed", context_id=context.context_id, actor=actor
                )
            )
            raise
        self.store.save_story(story)
        self.store.append_event(
            RequirementEvent(
                event_type="story_generation_completed",
                context_id=context.context_id,
                story_id=story.story_id,
                story_version=story.version,
                actor=actor,
            )
        )
        return story

    def regenerate_story(
        self,
        story_id: str,
        provider: StoryGenerationProvider,
        *,
        actor: str | None = None,
        generation_parameters: Mapping[str, Any] | None = None,
    ) -> CanonicalStory:
        """Replace a non-authoritative draft's content in a new immutable version."""

        current = self.store.get_story(story_id)
        if current.lifecycle_status == StoryLifecycleStatus.APPROVED:
            raise InvalidLifecycleTransitionError(
                "An approved story must be revised before it can be regenerated"
            )
        context = self.store.get_context(current.source_context_id)
        self.store.append_event(
            RequirementEvent(
                event_type="story_regeneration_requested",
                context_id=context.context_id,
                story_id=current.story_id,
                story_version=current.version,
                actor=actor,
            )
        )
        try:
            generated = self.generation_service.generate(context, provider, generation_parameters)
        except Exception:
            self.store.append_event(
                RequirementEvent(
                    event_type="story_regeneration_failed",
                    context_id=context.context_id,
                    story_id=current.story_id,
                    story_version=current.version,
                    actor=actor,
                )
            )
            raise
        regenerated = generated.model_copy(
            update={
                "story_id": current.story_id,
                "version": current.version + 1,
                "created_at": current.created_at,
                "updated_at": utc_now(),
                "reviewed_at": None,
                "reviewed_by": None,
                "approved_at": None,
                "approved_by": None,
                "revision_reason": "ai_regeneration",
            }
        )
        self.store.save_story(regenerated)
        self.store.append_event(
            RequirementEvent(
                event_type="story_regenerated",
                context_id=context.context_id,
                story_id=regenerated.story_id,
                story_version=regenerated.version,
                actor=actor,
            )
        )
        return regenerated

    @staticmethod
    def validate_story(story: CanonicalStory) -> StoryQualityReport:
        return validate_story_quality(story)

    def validate_stored_story(self, story_id: str, actor: str | None = None) -> StoryQualityReport:
        story = self.store.get_story(story_id)
        report = self.validate_story(story)
        self.store.append_event(
            RequirementEvent(
                event_type="story_validated",
                context_id=story.source_context_id,
                story_id=story.story_id,
                story_version=story.version,
                actor=actor,
                metadata={"valid": str(report.is_valid).lower()},
            )
        )
        return report

    def revise_story(
        self,
        story_id: str,
        changes: Mapping[str, Any],
        *,
        reviewer: str,
        reason: str = "human_revision",
    ) -> CanonicalStory:
        current = self.store.get_story(story_id)
        allowed_fields = set(GeneratedRequirementDraft.model_fields) | {
            "project_key",
            "issue_type",
            "story_points",
            "sprint",
            "reporter",
            "assignee",
            "parent_id",
            "parent_key",
            "epic_id",
            "epic_key",
            "fix_versions",
            "affects_versions",
            "status",
        }
        unknown = set(changes) - allowed_fields
        if unknown:
            raise RequirementValidationError(
                "Only requirement content may be revised; unsupported fields: "
                + ", ".join(sorted(unknown))
            )
        data = current.model_dump()
        data.update(changes)
        now = utc_now()
        data.update(
            version=current.version + 1,
            lifecycle_status=RequirementLifecycleStatus.DRAFT,
            reviewed_at=now,
            reviewed_by=reviewer,
            approved_at=None,
            approved_by=None,
            updated_at=now,
            revision_reason=reason,
        )
        revised = CanonicalRequirement.model_validate(data)

        self.store.save_story(revised)
        self.store.append_event(
            RequirementEvent(
                event_type="story_revised",
                context_id=revised.source_context_id,
                story_id=revised.story_id,
                story_version=revised.version,
                actor=reviewer,
            )
        )
        return revised

    def request_review(self, story_id: str, reviewer: str) -> CanonicalStory:
        current = self.store.get_story(story_id)
        if current.lifecycle_status not in {
            StoryLifecycleStatus.DRAFT,
            StoryLifecycleStatus.IN_REVIEW,
        }:
            raise InvalidLifecycleTransitionError("Only a draft can enter human review")
        updated = current.model_copy(
            update={
                "version": current.version + 1,
                "lifecycle_status": StoryLifecycleStatus.IN_REVIEW,
                "reviewed_by": reviewer,
                "reviewed_at": utc_now(),
                "updated_at": utc_now(),
                "revision_reason": "review_requested",
            }
        )
        self.store.save_story(updated)
        self.store.append_event(
            RequirementEvent(
                event_type="story_review_requested",
                story_id=updated.story_id,
                story_version=updated.version,
                actor=reviewer,
            )
        )
        return updated

    def approve_story(self, story_id: str, reviewer: str) -> CanonicalStory:
        current = self.store.get_story(story_id)
        if current.lifecycle_status not in {
            StoryLifecycleStatus.DRAFT,
            StoryLifecycleStatus.IN_REVIEW,
        }:
            raise InvalidLifecycleTransitionError("Only a draft or in-review story can be approved")
        report = validate_story_quality(current)
        if not report.is_valid:
            raise RequirementValidationError(
                "Story cannot be approved: " + "; ".join(issue.code for issue in report.errors)
            )
        now = utc_now()
        approved = current.model_copy(
            update={
                "version": current.version + 1,
                "lifecycle_status": StoryLifecycleStatus.APPROVED,
                "reviewed_at": now,
                "reviewed_by": reviewer,
                "approved_at": now,
                "approved_by": reviewer,
                "updated_at": now,
                "revision_reason": "human_approval",
            }
        )
        self.store.save_story(approved)
        self.store.append_event(
            RequirementEvent(
                event_type="story_approved",
                context_id=approved.source_context_id,
                story_id=approved.story_id,
                story_version=approved.version,
                actor=reviewer,
            )
        )
        return approved

    def reject_story(self, story_id: str, reviewer: str, reason: str) -> CanonicalStory:
        current = self.store.get_story(story_id)
        if current.lifecycle_status == StoryLifecycleStatus.APPROVED:
            raise InvalidLifecycleTransitionError(
                "An approved story must be revised before it can be rejected"
            )
        now = utc_now()
        rejected = current.model_copy(
            update={
                "version": current.version + 1,
                "lifecycle_status": StoryLifecycleStatus.REJECTED,
                "reviewed_at": now,
                "reviewed_by": reviewer,
                "updated_at": now,
                "revision_reason": reason,
            }
        )
        self.store.save_story(rejected)
        self.store.append_event(
            RequirementEvent(
                event_type="story_rejected",
                story_id=rejected.story_id,
                story_version=rejected.version,
                actor=reviewer,
            )
        )
        return rejected

    def promote_story(self, story_id: str) -> SDDSpecificationSeed:
        story = self.store.get_story(story_id)
        report = validate_story_quality(story)
        if not report.is_valid:
            raise RequirementValidationError(
                "Story cannot be promoted: " + "; ".join(issue.code for issue in report.errors)
            )
        seed = build_specification_seed(story)
        if self.seed_store:
            self.seed_store.save(seed)
        self.store.append_event(
            RequirementEvent(
                event_type="story_promoted_to_specification_seed",
                context_id=story.source_context_id,
                story_id=story.story_id,
                story_version=story.version,
                metadata={"promotion_id": seed.promotion_id},
            )
        )
        return seed

    def link_formal_specification(
        self, story_id: str, specification_id: str, *, actor: str
    ) -> CanonicalStory:
        """Attach the formal SDD artifact identifier without weakening the approval gate."""

        current = self.store.get_story(story_id)
        if current.lifecycle_status != StoryLifecycleStatus.APPROVED:
            raise InvalidLifecycleTransitionError(
                "Only an approved story can be linked to a formal SDD specification"
            )
        linked = current.model_copy(
            update={
                "version": current.version + 1,
                "parent_spec_id": specification_id,
                "updated_at": utc_now(),
                "revision_reason": "formal_specification_linked",
            }
        )
        self.store.save_story(linked)
        self.store.append_event(
            RequirementEvent(
                event_type="formal_specification_linked",
                context_id=linked.source_context_id,
                story_id=linked.story_id,
                story_version=linked.version,
                actor=actor,
                metadata={"specification_id": specification_id},
            )
        )
        return linked

    generate_requirement = generate_story
    regenerate_requirement = regenerate_story
    validate_requirement = validate_story
    validate_stored_requirement = validate_stored_story
    revise_requirement = revise_story
    request_requirement_review = request_review
    approve_requirement = approve_story
    reject_requirement = reject_story
    promote_requirement = promote_story
    link_formal_requirement = link_formal_specification

