from __future__ import annotations

import typer


def register_mcp_commands(app: typer.Typer) -> None:
    @app.command("mcp")
    def serve_mcp(
        transport: str = typer.Option(
            "stdio",
            "--transport",
            "-t",
            help=(
                "MCP transport protocol: 'stdio' (local/dev) or "
                "'streamable-http' (production ASGI)."
            ),
        ),
        host: str = typer.Option(
            "127.0.0.1",
            "--host",
            "-h",
            help="Host interface for Streamable HTTP transport.",
        ),
        port: int = typer.Option(
            8000,
            "--port",
            "-p",
            help="Port for Streamable HTTP transport.",
        ),
        path: str = typer.Option(
            "/mcp",
            "--path",
            help="Streamable HTTP endpoint path.",
        ),
    ) -> None:
        """Run the GAIN Model Context Protocol (MCP) Server."""
        from gain.mcp.server.app import create_mcp_server
        from gain.mcp.transports.http import run_streamable_http
        from gain.mcp.transports.stdio import run_stdio

        server = create_mcp_server()

        if transport == "stdio":
            typer.echo("Starting GAIN MCP Server over stdio transport...", err=True)
            run_stdio(server)
        elif transport in ("streamable-http", "http"):
            typer.echo(
                f"Starting GAIN MCP Server over Streamable HTTP on http://{host}:{port}{path}...",
                err=True,
            )
            run_streamable_http(server, host=host, port=port, streamable_http_path=path)
        else:
            raise typer.BadParameter(
                f"Unsupported transport '{transport}'. Choose 'stdio' or 'streamable-http'."
            )
