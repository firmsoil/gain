"""Tests for AI developer telemetry domain models and Parquet persistence."""

from datetime import UTC, datetime
from pathlib import Path

from gain.model.ai import AiDeveloperTelemetry, AiToolType
from gain.storage.ai_telemetry import (
    load_ai_telemetry_for_repo,
    read_ai_telemetry,
    write_ai_telemetry,
)


def test_ai_developer_telemetry_creation_and_acceptance_rate() -> None:
    telemetry = AiDeveloperTelemetry(
        developer_id="dev-alice",
        repository="firmsoil/gain",
        tool_type=AiToolType.COPILOT,
        window_start=datetime(2026, 1, 1, tzinfo=UTC),
        window_end=datetime(2026, 2, 1, tzinfo=UTC),
        active_days=22,
        suggestions_count=1000,
        acceptances_count=350,
        lines_suggested=5000,
        lines_accepted=1800,
        is_ai_active=True,
    )

    assert telemetry.developer_id == "dev-alice"
    assert telemetry.acceptance_rate == 0.35
    assert telemetry.tool_type == AiToolType.COPILOT


def test_ai_telemetry_parquet_roundtrip(tmp_path: Path) -> None:
    parquet_path = tmp_path / "ai_telemetry__test.parquet"
    records = [
        AiDeveloperTelemetry(
            developer_id="dev-1",
            repository="firmsoil/gain",
            suggestions_count=500,
            acceptances_count=150,
        ),
        AiDeveloperTelemetry(
            developer_id="dev-2",
            repository="other/project",
            suggestions_count=200,
            acceptances_count=80,
        ),
    ]

    write_ai_telemetry(records, parquet_path)
    loaded = read_ai_telemetry(parquet_path)

    assert len(loaded) == 2
    assert loaded[0].developer_id == "dev-1"
    assert loaded[0].acceptance_rate == 0.3
    assert loaded[1].developer_id == "dev-2"

    # Test load_ai_telemetry_for_repo
    repo_records = load_ai_telemetry_for_repo("firmsoil/gain", canonical_dir=tmp_path)
    assert len(repo_records) == 1
    assert repo_records[0].developer_id == "dev-1"
