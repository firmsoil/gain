from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from gain.cli import app
from gain.config import Settings
from gain.storage.analytics import write_canonical
from tests.factories import make_pr

runner = CliRunner()


def test_cli_config_check(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = Settings(
        github_token="ghp_test1234567890",
        github_repos=["test-org/repo-1"],
        data_dir=tmp_path / "data",
    )
    monkeypatch.setattr("gain.cli.get_settings", lambda: settings)
    monkeypatch.setattr("gain.cli.sync.get_settings", lambda: settings)

    result = runner.invoke(app, ["config-check"])
    assert result.exit_code == 0
    assert "GAIN configuration OK" in result.stdout
    assert "test-org/repo-1" in result.stdout


def test_cli_ai_impact(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    canonical_dir = tmp_path / "canonical"
    canonical_dir.mkdir(parents=True, exist_ok=True)
    pr = make_pr(repository_name_with_owner="firmsoil/gain", number=10)
    write_canonical([pr], canonical_dir / "prs.parquet")

    settings = Settings(canonical_dir=canonical_dir)
    monkeypatch.setattr("gain.cli.get_settings", lambda: settings)

    result = runner.invoke(app, ["ai-impact", "--repo", "firmsoil/gain", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "status" in payload


def test_cli_ai_roi(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    canonical_dir = tmp_path / "canonical"
    canonical_dir.mkdir(parents=True, exist_ok=True)
    pr = make_pr(repository_name_with_owner="firmsoil/gain", number=10)
    write_canonical([pr], canonical_dir / "prs.parquet")

    settings = Settings(canonical_dir=canonical_dir)
    monkeypatch.setattr("gain.cli.get_settings", lambda: settings)

    result = runner.invoke(app, ["ai-roi", "--population", "firmsoil/gain", "--devs", "10"])
    assert result.exit_code == 0
    assert "Modeled AI Tooling ROI:" in result.stdout


def test_cli_dora(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path,
        raw_dir=tmp_path / "raw",
        canonical_dir=tmp_path / "canonical",
        metrics_dir=tmp_path / "metrics",
    )
    monkeypatch.setattr("gain.cli.get_settings", lambda: settings)

    result = runner.invoke(app, ["dora", "--repo", "firmsoil/gain", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "status" in payload


def test_cli_issues(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path,
        raw_dir=tmp_path / "raw",
        canonical_dir=tmp_path / "canonical",
        metrics_dir=tmp_path / "metrics",
    )
    monkeypatch.setattr("gain.cli.get_settings", lambda: settings)

    result = runner.invoke(app, ["issues", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "status" in payload


def test_cli_requirements_flow(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    req_dir = tmp_path / "requirements"
    req_dir.mkdir(parents=True, exist_ok=True)
    settings = Settings(requirements_dir=req_dir)
    monkeypatch.setattr("gain.cli.get_settings", lambda: settings)
    monkeypatch.setattr("gain.cli.requirements.get_settings", lambda: settings)

    # 1. Create Context
    context_file = tmp_path / "context.json"
    context_file.write_text(
        json.dumps(
            {
                "context_id": "CTX-100",
                "title": "Checkout Performance",
                "business_problem": "High checkout latency causing drop-off",
                "business_goal": "Reduce checkout step to <500ms",
                "business_context": "Production checkout flow",
                "version": 1,
            }
        ),
        encoding="utf-8",
    )

    create_res = runner.invoke(
        app,
        ["requirements", "create-context", "--input-file", str(context_file), "--actor", "alice"],
    )
    assert create_res.exit_code == 0
    created_payload = json.loads(create_res.stdout)
    assert created_payload["context_id"] == "CTX-100"


def test_cli_compute_and_monthly_stats(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    canonical_dir = tmp_path / "canonical"
    canonical_dir.mkdir(parents=True, exist_ok=True)
    metrics_dir = tmp_path / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)

    pr = make_pr(repository_name_with_owner="firmsoil/gain", number=1)
    parquet_path = canonical_dir / "prs.parquet"
    write_canonical([pr], parquet_path)

    settings = Settings(canonical_dir=canonical_dir, metrics_dir=metrics_dir)
    monkeypatch.setattr("gain.cli.get_settings", lambda: settings)

    # 1. Compute
    compute_res = runner.invoke(app, ["compute", "--canonical-path", str(parquet_path)])
    assert compute_res.exit_code == 0
    assert "GAIN-PR-001" in compute_res.stdout

    # 2. Monthly Stats
    stats_res = runner.invoke(
        app, ["monthly-stats", "--canonical-path", str(parquet_path), "--output-format", "json"]
    )
    assert stats_res.exit_code == 0
    assert "GAIN-PR-010" in stats_res.stdout


def test_cli_ingest_adapters(tmp_path: Path) -> None:
    from gain.config import set_settings_override

    test_settings = Settings(
        data_dir=tmp_path,
        raw_dir=tmp_path / "raw",
        canonical_dir=tmp_path / "canonical",
        metrics_dir=tmp_path / "metrics",
    )
    set_settings_override(test_settings)
    try:
        # 1. Jira
        jira_file = tmp_path / "jira.json"
        jira_file.write_text(
            json.dumps(
                [
                    {
                        "id": "1001",
                        "key": "GAIN-1",
                        "fields": {
                            "summary": "Fix login crash",
                            "status": {"name": "Closed"},
                            "issuetype": {"name": "Bug"},
                            "created": "2026-06-01T10:00:00.000Z",
                        },
                    }
                ]
            ),
            encoding="utf-8",
        )
        jira_res = runner.invoke(
            app, ["ingest-jira", str(jira_file), "--project", "GAIN", "--json"]
        )
        assert jira_res.exit_code == 0

        # 2. Linear
        linear_file = tmp_path / "linear.json"
        linear_file.write_text(
            json.dumps(
                [
                    {
                        "id": "lin-1",
                        "identifier": "ENG-10",
                        "title": "Add caching",
                        "state": {"name": "Done"},
                        "createdAt": "2026-06-01T10:00:00.000Z",
                    }
                ]
            ),
            encoding="utf-8",
        )
        linear_res = runner.invoke(
            app, ["ingest-linear", str(linear_file), "--team", "ENG", "--json"]
        )
        assert linear_res.exit_code == 0

        # 3. Deployments
        deploy_file = tmp_path / "deploy.json"
        deploy_file.write_text(
            json.dumps(
                [
                    {
                        "deployment_id": "dep-1",
                        "environment": "production",
                        "status": "success",
                        "started_at": "2026-06-01T10:00:00Z",
                        "finished_at": "2026-06-01T10:05:00Z",
                    }
                ]
            ),
            encoding="utf-8",
        )
        deploy_res = runner.invoke(
            app,
            ["ingest-deployments", str(deploy_file), "--repo", "firmsoil/gain", "--json"],
        )
        assert deploy_res.exit_code == 0
    finally:
        set_settings_override(None)
