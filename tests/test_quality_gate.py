"""Tests for deterministic SE 3.0 CI/CD Quality Gate engine."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from gain.metrics.quality_gate import evaluate_quality_gate


def _make_sample_scorecard(
    bloat_pct: float = 0.0,
    refactor_ratio: float = 0.30,
    pure_adds_pct: float = 10.0,
    friction_pct: float = 5.0,
    hotfix_pct: float = 2.0,
    total_prs: int = 10,
) -> dict[str, Any]:
    return {
        "repository": "firmsoil/gain",
        "scan_run_id": "test-run-123",
        "evaluation_window_days": 90,
        "telemetry_overview": {
            "total_prs_evaluated": total_prs,
            "total_commits_evaluated": 20,
            "ai_assisted_prs": 2,
            "ai_penetration_rate": "20.0%",
            "detected_tools": ["GitHub Copilot"],
        },
        "code_quality_and_bloat": {
            "refactoring_ratio_metric": "GAIN-QUAL-003",
            "aggregate_refactoring_ratio": refactor_ratio,
            "pure_additions_percentage": pure_adds_pct,
            "code_bloat_metric": "GAIN-QUAL-004",
            "mean_net_additions_per_file": 12.0,
            "bloat_flagged_percentage": bloat_pct,
        },
        "verification_and_stability": {
            "verification_tax_metric": "GAIN-QUAL-005",
            "mean_review_latency_hours": 4.5,
            "high_friction_review_pct": friction_pct,
            "defect_rework_metric": "GAIN-QUAL-006",
            "hotfix_pr_percentage": hotfix_pct,
        },
    }


def test_quality_gate_passes_healthy_scorecard() -> None:
    scorecard = _make_sample_scorecard()
    res = evaluate_quality_gate(scorecard)
    assert res.passed is True
    assert len(res.violations) == 0


def test_quality_gate_fails_excessive_bloat() -> None:
    scorecard = _make_sample_scorecard(bloat_pct=35.0)
    res = evaluate_quality_gate(scorecard, max_bloat_pct=25.0)
    assert res.passed is False
    assert any("Code Bloat Gate" in v for v in res.violations)


def test_quality_gate_fails_additive_bias() -> None:
    scorecard = _make_sample_scorecard(
        refactor_ratio=0.02,
        pure_adds_pct=95.0,
        total_prs=15,
    )
    res = evaluate_quality_gate(scorecard, min_refactor_ratio=0.10)
    assert res.passed is False
    assert any("Additive Bias Gate" in v for v in res.violations)


def test_quality_gate_fails_high_review_friction() -> None:
    scorecard = _make_sample_scorecard(friction_pct=45.0, total_prs=10)
    res = evaluate_quality_gate(scorecard, max_friction_pct=30.0)
    assert res.passed is False
    assert any("Verification Tax Gate" in v for v in res.violations)


def test_quality_gate_fails_high_defect_rework() -> None:
    scorecard = _make_sample_scorecard(hotfix_pct=30.0, total_prs=10)
    res = evaluate_quality_gate(scorecard, max_hotfix_pct=25.0)
    assert res.passed is False
    assert any("Defect Rework Gate" in v for v in res.violations)


def test_quality_gate_cli_subprocess(tmp_path: Path) -> None:
    scorecard_path = tmp_path / "scorecard.json"
    scorecard_path.write_text(json.dumps(_make_sample_scorecard()), encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, "scripts/evaluate_quality_gate.py", "--input", str(scorecard_path)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "ALL SE 3.0 QUALITY GATES PASSED" in proc.stdout
