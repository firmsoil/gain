from __future__ import annotations

from gain.errors import RequirementValidationError
from gain.requirements.models import CanonicalStory, SDDSpecificationSeed, StoryLifecycleStatus


def build_specification_seed(story: CanonicalStory) -> SDDSpecificationSeed:
    """Create an SDD input artifact without pretending that it is the formal specification."""

    if story.lifecycle_status != StoryLifecycleStatus.APPROVED:
        raise RequirementValidationError(
            "Only an approved story can be promoted to an SDD specification seed"
        )
    return SDDSpecificationSeed(
        requirement_id=story.requirement_id,
        requirement_version=story.version,
        source_context_id=story.source_context_id,
        source_context_version=story.source_context_version,
        external_references=list(story.external_references),
        product_requirements={
            "summary": story.summary,
            "description": story.description,
            "role": story.role,
            "capability": story.capability,
            "business_value": story.business_value,
            "preconditions": story.preconditions,
            "risks": story.risks,
        },
        acceptance_criteria=story.acceptance_criteria,
        assumptions=story.assumptions,
        dependencies=story.dependencies,
        open_questions=story.open_questions,
        ambiguity_flags=story.ambiguity_flags,
        human_approval={
            "approved_by": story.approved_by,
            "approved_at": story.approved_at.isoformat() if story.approved_at else None,
            "reviewed_by": story.reviewed_by,
            "reviewed_at": story.reviewed_at.isoformat() if story.reviewed_at else None,
        },
        ai_provenance={
            "generation_id": story.generation_id,
            "model_provider": story.model_provider,
            "model_name": story.model_name,
            "model_version": story.model_version,
            "prompt_template_version": story.prompt_template_version,
            "input_hash": story.input_hash,
            "output_hash": story.output_hash,
            "generated_at": story.generated_at.isoformat() if story.generated_at else None,
        },
    )
