from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import typer


def register_demo_commands(app: typer.Typer) -> None:
    @app.command("demo")
    def cli_demo(
        data_dir: Path | None = typer.Option(
            None,
            "--data-dir",
            "-d",
            help="Optional destination root directory for synthetic demo data.",
        ),
    ) -> None:
        """Run an end-to-end interactive demo across all GAIN capabilities
        using synthetic telemetry.
        """
        scripts_dir = Path(__file__).resolve().parent.parent.parent.parent / "scripts"
        demo_path = scripts_dir / "demo_gain_platform.py"
        if not demo_path.is_file():
            typer.echo(f"Error: Demo script not found at {demo_path}", err=True)
            raise typer.Exit(code=1)

        spec = importlib.util.spec_from_file_location("demo_gain_platform", demo_path)
        if spec is None or spec.loader is None:
            typer.echo("Error: Unable to load demo script", err=True)
            raise typer.Exit(code=1)

        module = importlib.util.module_from_spec(spec)
        sys.modules["demo_gain_platform"] = module
        spec.loader.exec_module(module)
        module.run_demo(data_root=data_dir)
