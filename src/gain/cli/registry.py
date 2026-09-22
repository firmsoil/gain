from __future__ import annotations

import json

import typer

from gain.config import get_settings
from gain.logging import configure_logging
from gain.registry import RepoEntry, RepositoryDiscovery, RepositoryRegistry


def register_registry_commands(registry_app: typer.Typer) -> None:
    @registry_app.command("list")
    def registry_list(
        org: str | None = typer.Option(
            None, "--org", "-o", help="Filter repositories by organization."
        ),
        tier: str | None = typer.Option(None, "--tier", "-t", help="Filter repositories by tier."),
        json_output: bool = typer.Option(False, "--json", help="Output raw JSON payload."),
    ) -> None:
        """List registered repositories, optionally filtered by org or tier."""
        configure_logging()
        settings = get_settings()
        settings.ensure_directories()
        registry = RepositoryRegistry(settings.registry_path)
        entries = registry.list_all()
        if org is not None:
            entries = [e for e in entries if e.org_id.lower() == org.strip().lower()]
        if tier is not None:
            entries = [e for e in entries if e.tier.lower() == tier.strip().lower()]

        if json_output:
            typer.echo(json.dumps([e.model_dump(mode="json") for e in entries], indent=2))
            return

        if not entries:
            typer.echo("No repositories found in registry.")
            return

        typer.echo(f"Repositories ({len(entries)}):")
        for entry in entries:
            synced_str = entry.last_synced_at.isoformat() if entry.last_synced_at else "never"
            archived_str = " [archived]" if entry.is_archived else ""
            typer.echo(
                f"- {entry.name_with_owner} [tier={entry.tier}] [org={entry.org_id}] "
                f"[branch={entry.default_branch}] [last_synced={synced_str}]{archived_str}"
            )

    @registry_app.command("add")
    def registry_add(
        name: str = typer.Argument(
            ..., help="Repository name in 'owner/name' format or repository name."
        ),
        tier: str = typer.Option(
            "standard", "--tier", "-t", help="Repository tier ('critical', 'standard', 'archive')."
        ),
        org: str | None = typer.Option(
            None, "--org", "-o", help="Organization name (inferred from name if 'owner/name')."
        ),
        team: str | None = typer.Option(None, "--team", help="Optional team ID."),
        branch: str = typer.Option("main", "--branch", "-b", help="Default branch name."),
    ) -> None:
        """Add or update a repository in the registry."""
        configure_logging()
        settings = get_settings()
        settings.ensure_directories()

        name_clean = name.strip()
        if "/" in name_clean:
            parts = [p.strip() for p in name_clean.split("/")]
            if len(parts) != 2 or not parts[0] or not parts[1]:
                raise typer.BadParameter(
                    f"Invalid repository identifier '{name_clean}'; expected 'owner/name'."
                )
            resolved_org = org.strip() if org else parts[0]
            name_with_owner = f"{resolved_org}/{parts[1]}"
        else:
            if not org:
                raise typer.BadParameter(
                    "Organization must be specified via --org if NAME is not "
                    "in 'owner/repo' format."
                )
            resolved_org = org.strip()
            name_with_owner = f"{resolved_org}/{name_clean}"

        registry = RepositoryRegistry(settings.registry_path)
        existing = registry.get(name_with_owner)
        last_synced = existing.last_synced_at if existing else None
        is_archived = existing.is_archived if existing else False

        try:
            entry = RepoEntry(
                name_with_owner=name_with_owner,
                org_id=resolved_org,
                team_id=team.strip() if team else None,
                tier=tier.strip(),
                last_synced_at=last_synced,
                is_archived=is_archived,
                default_branch=branch.strip(),
            )
        except Exception as exc:
            raise typer.BadParameter(str(exc)) from exc

        registry.add_or_update(entry)
        registry.save()
        typer.echo(
            f"Added repository {entry.name_with_owner} "
            f"(tier={entry.tier}, org={entry.org_id}) to registry."
        )

    @registry_app.command("discover")
    def registry_discover(
        org: str = typer.Argument(
            ..., help="GitHub organization name to discover repositories for."
        ),
        tier: str = typer.Option(
            "standard", "--tier", "-t", help="Tier to assign to discovered repos."
        ),
        token: str | None = typer.Option(None, "--token", help="GitHub personal access token."),
        save: bool = typer.Option(
            True, "--save/--no-save", help="Save discovered repositories to registry."
        ),
    ) -> None:
        """Discover repositories for an organization from GitHub and optionally register them."""
        configure_logging()
        settings = get_settings()
        settings.ensure_directories()

        auth_token = token or settings.github_token
        discovery = RepositoryDiscovery(token=auth_token, org=org)
        try:
            discovered = discovery.discover(tier=tier)
        except Exception as exc:
            typer.echo(f"Error discovering repositories: {exc}", err=True)
            raise typer.Exit(code=1) from exc

        typer.echo(f"Discovered {len(discovered)} repositories for org '{org}':")
        for r in discovered:
            typer.echo(f"- {r.name_with_owner} [tier={r.tier}] [branch={r.default_branch}]")

        if save and discovered:
            registry = RepositoryRegistry(settings.registry_path)
            registry.add_batch(discovered)
            registry.save()
            typer.echo(
                f"Saved {len(discovered)} repositories to registry at {settings.registry_path}."
            )
