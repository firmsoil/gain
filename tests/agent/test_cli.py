"""Unit tests for GAIN Agent CLI subcommands."""

import json

from typer.testing import CliRunner

from gain.cli import app
from gain.config import Settings

runner = CliRunner()


def test_cli_agent_ask(populated_env: Settings) -> None:
    result = runner.invoke(
        app, ["agent", "ask", "What is our PR cycle time?", "-r", "firmsoil/gain"]
    )
    assert result.exit_code == 0
    assert "Engineering Intelligence Investigation Briefing" in result.stdout
    assert "[Derived]" in result.stdout


def test_cli_agent_investigate_text(populated_env: Settings) -> None:
    result = runner.invoke(
        app, ["agent", "investigate", "Investigate delivery bottlenecks", "-r", "firmsoil/gain"]
    )
    assert result.exit_code == 0
    assert "Evidence Package:" in result.stdout
    assert "Investigation ID:" in result.stdout
    assert "Total Classified Claims:" in result.stdout


def test_cli_agent_investigate_json(populated_env: Settings) -> None:
    result = runner.invoke(
        app,
        [
            "agent",
            "investigate",
            "Investigate delivery bottlenecks",
            "-r",
            "firmsoil/gain",
            "--json",
        ],
    )
    assert result.exit_code == 0
    json_start = result.stdout.find("{")
    assert json_start != -1
    payload = json.loads(result.stdout[json_start:])
    assert payload["status"] == "completed"
    assert "investigation_id" in payload
    assert "claims" in payload
    assert len(payload["claims"]) > 0
