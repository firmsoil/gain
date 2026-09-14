from __future__ import annotations

import json
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from gain.requirements.models import (
    BusinessContext,
    CanonicalStory,
    RequirementEvent,
    SDDSpecificationSeed,
)

ModelT = TypeVar("ModelT", bound=BaseModel)


class RequirementsStore:
    """Append-only JSON persistence matching GAIN's existing file-backed storage approach."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.contexts_dir = root / "contexts"
        self.stories_dir = root / "stories"
        self.events_path = root / "events.jsonl"
        for path in (self.contexts_dir, self.stories_dir):
            path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _write_versioned(model: BaseModel, directory: Path, version: int) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"v{version}.json"
        if path.exists():
            raise FileExistsError(f"Immutable requirements artifact already exists: {path}")
        path.write_text(
            json.dumps(model.model_dump(mode="json"), indent=2, sort_keys=True), encoding="utf-8"
        )
        return path

    @staticmethod
    def _read_versioned(model_type: type[ModelT], directory: Path, version: int) -> ModelT:
        path = directory / f"v{version}.json"
        if not path.exists():
            raise FileNotFoundError(path)
        return model_type.model_validate_json(path.read_text(encoding="utf-8"))

    @staticmethod
    def _versions(directory: Path) -> list[int]:
        versions: list[int] = []
        for path in directory.glob("v*.json"):
            try:
                versions.append(int(path.stem.removeprefix("v")))
            except ValueError:
                continue
        return sorted(versions)

    def save_context(self, context: BusinessContext) -> Path:
        return self._write_versioned(
            context, self.contexts_dir / context.context_id, context.version
        )

    def get_context(self, context_id: str, version: int | None = None) -> BusinessContext:
        directory = self.contexts_dir / context_id
        selected_version = version or self._latest_version(directory)
        return self._read_versioned(BusinessContext, directory, selected_version)

    def save_story(self, story: CanonicalStory) -> Path:
        return self._write_versioned(story, self.stories_dir / story.story_id, story.version)

    def get_story(self, story_id: str, version: int | None = None) -> CanonicalStory:
        directory = self.stories_dir / story_id
        selected_version = version or self._latest_version(directory)
        return self._read_versioned(CanonicalStory, directory, selected_version)

    def story_history(self, story_id: str) -> list[CanonicalStory]:
        directory = self.stories_dir / story_id
        return [
            self._read_versioned(CanonicalStory, directory, version)
            for version in self._versions(directory)
        ]

    save_requirement = save_story
    get_requirement = get_story
    requirement_history = story_history

    def append_event(self, event: RequirementEvent) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.model_dump(mode="json"), sort_keys=True))
            handle.write("\n")

    @staticmethod
    def _latest_version(directory: Path) -> int:
        versions = RequirementsStore._versions(directory)
        if not versions:
            raise FileNotFoundError(directory)
        return versions[-1]


class SpecificationSeedStore:
    """Storage for promotion records; separate from formal SDD artifacts by design."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, seed: SDDSpecificationSeed) -> Path:
        path = self.root / f"{seed.promotion_id}.json"
        if path.exists():
            raise FileExistsError(f"Immutable specification seed already exists: {path}")
        path.write_text(
            json.dumps(seed.model_dump(mode="json"), indent=2, sort_keys=True), encoding="utf-8"
        )
        return path

    def find_for_story(self, story_id: str) -> list[SDDSpecificationSeed]:
        seeds: list[SDDSpecificationSeed] = []
        for path in sorted(self.root.glob("*.json")):
            seed = SDDSpecificationSeed.model_validate_json(path.read_text(encoding="utf-8"))
            if seed.story_id == story_id or seed.requirement_id == story_id:
                seeds.append(seed)
        return seeds

    find_for_requirement = find_for_story

