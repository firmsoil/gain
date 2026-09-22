from __future__ import annotations

import json
from pathlib import Path

import typer

from gain.logging import configure_logging


def register_adapter_commands(app: typer.Typer) -> None:
    @app.command("ingest-jira")
    def cli_ingest_jira(
        file_path: str = typer.Argument(..., help="Path to JSON file containing Jira issues."),
        project: str = typer.Option("default", "--project", "-p", help="Jira project key."),
        json_output: bool = typer.Option(False, "--json", help="Output summary as JSON."),
    ) -> None:
        """Ingest Jira issues through enterprise source adapter into canonical storage."""
        from gain.adapters.jira import JiraSourceAdapter

        configure_logging()
        path = Path(file_path)
        if not path.exists():
            typer.echo(f"Error: file not found: {file_path}", err=True)
            raise typer.Exit(1)

        with open(path, encoding="utf-8") as f:
            payloads = json.load(f)
        if not isinstance(payloads, list):
            payloads = [payloads]

        adapter = JiraSourceAdapter()
        result = adapter.ingest_payloads(payloads, partition_key=project)
        if json_output:
            typer.echo(json.dumps(result.model_dump(mode="json"), indent=2))
        else:
            typer.echo(
                f"Jira Ingestion Complete: {result.canonical_records_count} issues canonicalized"
            )
            typer.echo(f"Quarantined Errors: {result.errors_count}")
            typer.echo(f"Canonical Storage: {result.canonical_file_path}")

    @app.command("ingest-linear")
    def cli_ingest_linear(
        file_path: str = typer.Argument(..., help="Path to JSON file containing Linear issues."),
        team: str = typer.Option("default", "--team", "-t", help="Linear team key."),
        json_output: bool = typer.Option(False, "--json", help="Output summary as JSON."),
    ) -> None:
        """Ingest Linear issues through enterprise source adapter into canonical storage."""
        from gain.adapters.linear import LinearSourceAdapter

        configure_logging()
        path = Path(file_path)
        if not path.exists():
            typer.echo(f"Error: file not found: {file_path}", err=True)
            raise typer.Exit(1)

        with open(path, encoding="utf-8") as f:
            payloads = json.load(f)
        if not isinstance(payloads, list):
            payloads = [payloads]

        adapter = LinearSourceAdapter()
        result = adapter.ingest_payloads(payloads, partition_key=team)
        if json_output:
            typer.echo(json.dumps(result.model_dump(mode="json"), indent=2))
        else:
            typer.echo(
                f"Linear Ingestion Complete: {result.canonical_records_count} issues canonicalized"
            )
            typer.echo(f"Quarantined Errors: {result.errors_count}")

    @app.command("ingest-deployments")
    def cli_ingest_deployments(
        file_path: str = typer.Argument(
            ..., help="Path to JSON file containing deployment events."
        ),
        repo: str = typer.Option("firmsoil/gain", "--repo", "-r", help="Repository identifier."),
        json_output: bool = typer.Option(False, "--json", help="Output summary as JSON."),
    ) -> None:
        """Ingest CI/CD deployment events into canonical storage."""
        from gain.adapters.deployments import DeploymentSourceAdapter

        configure_logging()
        path = Path(file_path)
        if not path.exists():
            typer.echo(f"Error: file not found: {file_path}", err=True)
            raise typer.Exit(1)

        with open(path, encoding="utf-8") as f:
            payloads = json.load(f)
        if not isinstance(payloads, list):
            payloads = [payloads]

        adapter = DeploymentSourceAdapter()
        result = adapter.ingest_payloads(payloads, partition_key=repo.replace("/", "__"))
        if json_output:
            typer.echo(json.dumps(result.model_dump(mode="json"), indent=2))
        else:
            typer.echo(
                f"Deployment Ingestion Complete: {result.canonical_records_count} "
                "deployments canonicalized"
            )
            typer.echo(f"Quarantined Errors: {result.errors_count}")
