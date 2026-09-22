from __future__ import annotations

import json

import typer


def register_agent_commands(agent_app: typer.Typer) -> None:
    @agent_app.command("ask")
    def agent_ask(
        query: str = typer.Argument(
            ..., help="Natural-language question to ask the Engineering Intelligence Agent."
        ),
        repo: str = typer.Option(
            "firmsoil/gain", "--repo", "-r", help="Target repository name with owner."
        ),
    ) -> None:
        """Ask an engineering intelligence question with policy guard and evidence verification."""
        import asyncio

        from gain.agent.orchestrator import EngineeringIntelligenceAgent

        agent = EngineeringIntelligenceAgent()
        resp = asyncio.run(agent.investigate(query=query, default_repo=repo))
        typer.echo(resp.summary)

    @agent_app.command("investigate")
    def agent_investigate(
        query: str = typer.Argument(..., help="Engineering question or hypothesis to investigate."),
        repo: str = typer.Option(
            "firmsoil/gain", "--repo", "-r", help="Target repository name with owner."
        ),
        json_output: bool = typer.Option(
            False, "--json", help="Output full structured JSON report."
        ),
    ) -> None:
        """Run an end-to-end multi-step engineering investigation and build an evidence package."""
        import asyncio

        from gain.agent.orchestrator import EngineeringIntelligenceAgent

        agent = EngineeringIntelligenceAgent()
        resp = asyncio.run(agent.investigate(query=query, default_repo=repo))

        if json_output:
            typer.echo(json.dumps(resp.model_dump(mode="json"), indent=2))
        else:
            typer.echo(resp.summary)
            typer.echo("")
            typer.echo(f"Evidence Package: {resp.evidence_package_id}")
            typer.echo(f"Investigation ID: {resp.investigation_id}")
            typer.echo(f"Total Classified Claims: {len(resp.claims)}")
