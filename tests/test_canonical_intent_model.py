"""Tests for CanonicalIntent domain model and Parquet storage (SE 3.0 Intent Archiving)."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from gain.model.intent import (
    CanonicalIntent,
    ClarificationType,
    EpistemicTier,
    IntentSpeaker,
    IntentStatus,
    IntentTurn,
)
from gain.storage.intents import (
    load_intents_for_repo,
    read_canonical_intents,
    write_canonical_intents,
)


def test_canonical_intent_creation_and_utc_enforcement() -> None:
    t0 = datetime(2026, 4, 1, 10, 0, 0)  # naive datetime
    t1 = datetime(2026, 4, 1, 10, 15, 0)  # naive datetime

    turn = IntentTurn(
        speaker=IntentSpeaker.HUMAN,
        content="I need a deterministic service for refactoring metrics.",
        timestamp=t0,
        clarification_type=ClarificationType.GOAL_REFINEMENT,
    )
    assert turn.timestamp.tzinfo == UTC

    intent = CanonicalIntent(
        id="intent-001",
        repository="firmsoil/gain",
        author_id="architect@firmsoil.com",
        title="Implement Refactoring Ratio Metric",
        raw_prompt="Add refactoring ratio metric to detect code bloat",
        aligned_specification="Deterministic pure Python metric GAIN-QUAL-003...",
        acceptance_criteria=[
            "Pure additions evaluate to refactoring_ratio 0.0",
            "Deletions divided by total churn",
        ],
        synthesized_test_identifiers=["test_refactoring_ratio_metric_calculations"],
        dialogue_history=[turn],
        status=IntentStatus.ALIGNED,
        epistemic_tier=EpistemicTier.OBSERVED,
        linked_pr_numbers=[101],
        linked_issue_keys=["ENG-55"],
        created_at=t0,
        aligned_at=t1,
        collected_at=t1,
        ingestion_run_id="run-intent-01",
    )

    assert intent.created_at.tzinfo == UTC
    assert intent.aligned_at is not None
    assert intent.aligned_at.tzinfo == UTC
    assert intent.is_aligned is True
    assert intent.turn_count == 1
    assert intent.alignment_duration_seconds() == 900.0  # 15 minutes = 900s

    # Immutability check
    with pytest.raises(ValidationError):
        intent.title = "Mutated Title"

    # Extra forbid check
    with pytest.raises(ValidationError):
        CanonicalIntent(
            id="intent-bad",
            repository="firmsoil/gain",
            author_id="dev",
            title="Bad",
            raw_prompt="Bad",
            created_at=t0,
            collected_at=t0,
            ingestion_run_id="run-bad",
            unexpected_field="disallowed",  # type: ignore[call-arg]
        )


def test_intent_alignment_unaligned_duration() -> None:
    t0 = datetime(2026, 4, 1, 10, 0, 0, tzinfo=UTC)
    intent = CanonicalIntent(
        id="intent-002",
        repository="firmsoil/gain",
        author_id="dev",
        title="Work in progress",
        raw_prompt="Drafting a new module",
        status=IntentStatus.ALIGNING,
        created_at=t0,
        aligned_at=None,
        collected_at=t0,
        ingestion_run_id="run-02",
    )
    assert intent.is_aligned is False
    assert intent.alignment_duration_seconds() is None


def test_parquet_roundtrip_canonical_intents(tmp_path: Path) -> None:
    t0 = datetime(2026, 4, 1, 9, 0, 0, tzinfo=UTC)
    t1 = t0 + timedelta(minutes=5)
    t2 = t0 + timedelta(minutes=10)

    turns = [
        IntentTurn(
            speaker=IntentSpeaker.HUMAN,
            content="Can we isolate confounding factors in AI impact analysis?",
            timestamp=t0,
            clarification_type=ClarificationType.GOAL_REFINEMENT,
        ),
        IntentTurn(
            speaker=IntentSpeaker.ASSISTANT,
            content="We should control for PR size disparity and repository size.",
            timestamp=t1,
            clarification_type=ClarificationType.CONSTRAINT,
        ),
        IntentTurn(
            speaker=IntentSpeaker.HUMAN,
            content="Agreed. Let's add size disparity flag when delta > 25%.",
            timestamp=t2,
            clarification_type=ClarificationType.ACCEPTANCE_CRITERIA,
        ),
    ]

    intent1 = CanonicalIntent(
        id="intent-rt-1",
        repository="firmsoil/gain",
        author_id="user-1",
        title="Confounder isolation in AI Impact",
        raw_prompt="Isolate confounders",
        aligned_specification="Check size disparity across cohorts",
        acceptance_criteria=["Flag size disparity if > 25%"],
        synthesized_test_identifiers=["test_ai_impact_confounder_size"],
        dialogue_history=turns,
        status=IntentStatus.ALIGNED,
        epistemic_tier=EpistemicTier.DERIVED,
        linked_pr_numbers=[201, 202],
        linked_issue_keys=["ENG-99"],
        created_at=t0,
        aligned_at=t2,
        collected_at=t2,
        ingestion_run_id="run-rt",
    )

    intent2 = CanonicalIntent(
        id="intent-rt-2",
        repository="acme/service",
        author_id="user-2",
        title="Other repository intent",
        raw_prompt="Configure linting",
        status=IntentStatus.DRAFT,
        epistemic_tier=EpistemicTier.OBSERVED,
        created_at=t0,
        collected_at=t0,
        ingestion_run_id="run-rt",
    )

    parquet_file = tmp_path / "intents__01.parquet"
    write_canonical_intents([intent1, intent2], parquet_file)

    loaded = read_canonical_intents(parquet_file)
    assert len(loaded) == 2

    l1 = loaded[0]
    assert l1.id == "intent-rt-1"
    assert l1.repository == "firmsoil/gain"
    assert l1.turn_count == 3
    assert l1.acceptance_criteria == ["Flag size disparity if > 25%"]
    assert l1.synthesized_test_identifiers == ["test_ai_impact_confounder_size"]
    assert l1.dialogue_history[1].speaker == IntentSpeaker.ASSISTANT
    assert l1.dialogue_history[1].clarification_type == ClarificationType.CONSTRAINT
    assert l1.alignment_duration_seconds() == 600.0


def test_load_intents_for_repo_filtering(tmp_path: Path) -> None:
    canonical_dir = tmp_path / "canonical"
    canonical_dir.mkdir(parents=True, exist_ok=True)

    t0 = datetime(2026, 4, 1, 9, 0, 0, tzinfo=UTC)
    intents = [
        CanonicalIntent(
            id="intent-f1",
            repository="firmsoil/gain",
            author_id="alice",
            title="GAIN feature",
            raw_prompt="Add feature",
            status=IntentStatus.ALIGNED,
            created_at=t0,
            aligned_at=t0,
            collected_at=t0,
            ingestion_run_id="run-1",
        ),
        CanonicalIntent(
            id="intent-o1",
            repository="other/repo",
            author_id="bob",
            title="Other feature",
            raw_prompt="Add other",
            status=IntentStatus.DRAFT,
            created_at=t0,
            collected_at=t0,
            ingestion_run_id="run-1",
        ),
    ]

    write_canonical_intents(intents, canonical_dir / "intents__01.parquet")

    gain_intents = load_intents_for_repo(repository="firmsoil/gain", canonical_dir=canonical_dir)
    assert len(gain_intents) == 1
    assert gain_intents[0].id == "intent-f1"

    all_intents = load_intents_for_repo(repository=None, canonical_dir=canonical_dir)
    assert len(all_intents) == 2
