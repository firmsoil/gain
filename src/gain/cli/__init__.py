from __future__ import annotations

import typer

from gain.cli.adapters import register_adapter_commands
from gain.cli.agent import register_agent_commands
from gain.cli.demo import register_demo_commands
from gain.cli.maintenance import register_maintenance_commands
from gain.cli.mcp import register_mcp_commands
from gain.cli.metrics import register_metrics_commands
from gain.cli.registry import register_registry_commands
from gain.cli.requirements import register_requirements_commands
from gain.cli.sync import register_sync_commands
from gain.config import Settings, get_settings
from gain.logging import configure_logging

app = typer.Typer(help="GAIN — GitHub AI Intelligence Network")
requirements_app = typer.Typer(help="Human-governed requirements → Jira → SDD operations.")
agent_app = typer.Typer(help="Engineering Intelligence Agent operations.")
registry_app = typer.Typer(help="Repository Registry operations.")
maintenance_app = typer.Typer(help="Storage maintenance, retention policies, and compaction.")

# Register sub-typers
app.add_typer(requirements_app, name="requirements")
app.add_typer(agent_app, name="agent")
app.add_typer(registry_app, name="registry")
app.add_typer(maintenance_app, name="maintenance")

# Register commands on respective apps
register_sync_commands(app)
register_metrics_commands(app)
register_adapter_commands(app)
register_mcp_commands(app)
register_demo_commands(app)
register_requirements_commands(requirements_app)
register_agent_commands(agent_app)
register_registry_commands(registry_app)
register_maintenance_commands(maintenance_app)

__all__ = [
    "app",
    "requirements_app",
    "agent_app",
    "registry_app",
    "maintenance_app",
    "get_settings",
    "configure_logging",
    "Settings",
]
