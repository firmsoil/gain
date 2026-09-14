from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

from pydantic import ValidationError

from gain.errors import RequirementValidationError
from gain.requirements.models import (
    BusinessContext,
    CanonicalRequirement,
    GeneratedRequirementDraft,
    new_id,
    utc_now,
)

PROMPT_TEMPLATE_VERSION = "story-generation-v1"
_PROMPT_PATH = Path(__file__).with_name("prompts") / "story_generation_v1.md"


class StoryGenerationProvider(Protocol):
    """Provider boundary; implementations can use OpenAI, Anthropic, or another structured LLM."""

    provider_name: str
    model_name: str
    model_version: str | None

    def generate(self, prompt: str) -> Mapping[str, Any]: ...


RequirementGenerationProvider = StoryGenerationProvider


class StaticStoryProvider:
    """Deterministic provider for contract tests and offline operator workflows."""

    provider_name = "static-json"
    model_name = "static-json"
    model_version: str | None = "1"

    def __init__(self, response: Mapping[str, Any]) -> None:
        self._response = response

    def generate(self, prompt: str) -> Mapping[str, Any]:
        del prompt
        return self._response


StaticRequirementProvider = StaticStoryProvider


def canonical_json_hash(value: Any) -> str:
    serialized = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def render_generation_prompt(context: BusinessContext) -> str:
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    context_json = json.dumps(context.model_dump(mode="json"), indent=2, sort_keys=True)
    return template.replace("{business_context_json}", context_json)


class StoryGenerationService:
    """Turns explicit human context into a schema-validated, non-authoritative requirement draft."""

    def generate(
        self,
        context: BusinessContext,
        provider: StoryGenerationProvider,
        generation_parameters: Mapping[str, Any] | None = None,
    ) -> CanonicalRequirement:
        prompt = render_generation_prompt(context)
        raw_output = provider.generate(prompt)
        try:
            draft = GeneratedRequirementDraft.model_validate(raw_output)
        except ValidationError as exc:
            raise RequirementValidationError(
                "Story provider returned an invalid structured draft"
            ) from exc

        generated_at = utc_now()
        return CanonicalRequirement(
            **draft.model_dump(),
            source_context_id=context.context_id,
            source_context_version=context.version,
            generation_id=new_id(),
            model_provider=provider.provider_name,
            model_name=provider.model_name,
            model_version=provider.model_version,
            prompt_template_version=PROMPT_TEMPLATE_VERSION,
            generation_parameters=dict(generation_parameters or {}),
            input_hash=canonical_json_hash(context.model_dump(mode="json")),
            output_hash=canonical_json_hash(draft.model_dump(mode="json")),
            generated_at=generated_at,
            created_at=generated_at,
            updated_at=generated_at,
        )


RequirementGenerationService = StoryGenerationService

