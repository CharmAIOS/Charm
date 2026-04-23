import importlib.metadata
import json
import time
from pathlib import Path
from typing import Optional

import logging

import typer

from .commands import auth, config, init, logs, push, run, validate
from . import state

# Initialize the main Typer application with help text.
app = typer.Typer(
    name="charm",
    help="Charm CLI - The Universal Agent Runtime Manager",
    add_completion=False,
    no_args_is_help=True,
)

# Register command groups (sub-commands).
app.add_typer(auth.app, name="auth", help="Login, logout, and manage credentials")
app.add_typer(config.app, name="config", help="Manage local configuration")

# Register top-level commands.
app.command(name="init")(init.init_command)
app.command(name="run")(run.run_command)
app.command(name="validate")(validate.validate_command)
app.command(name="push")(push.push_command)
app.command(name="logs")(logs.logs_command)


def version_callback(value: bool):
    """Callback to display the current CLI version."""
    if value:
        # Check for updates first
        check_for_updates()
        try:
            version = importlib.metadata.version("charmos")
        except importlib.metadata.version.PackageNotFoundError:
            version = "dev"
        typer.echo(f"Charm CLI Version: {version}")
        raise typer.Exit()


def check_for_updates():
    """Silently check PyPI for updates at most once a day."""
    try:
        import httpx
        from rich.console import Console
        
        current_version_str = importlib.metadata.version("charmos")
        
        # Parse version strings into lists of ints for safe comparison, ignoring post-release tags
        def parse_ver(v: str):
            clean = "".join(c for c in v if c.isdigit() or c == ".")
            return [int(x) for x in clean.split(".") if x]
            
        current_ver = parse_ver(current_version_str)
        cache_file = Path.home() / ".charm" / ".update_check.json"
        
        if cache_file.exists():
            try:
                data = json.loads(cache_file.read_text())
                if time.time() - data.get("last_check", 0) < 86400:
                    return
            except Exception:
                pass
                
        # Fast network check (1 second timeout to avoid CLI hanging)
        with httpx.Client(timeout=1.0) as client:
            resp = client.get("https://pypi.org/pypi/charmos/json")
            if resp.status_code == 200:
                latest_version_str = resp.json()["info"]["version"]
                latest_ver = parse_ver(latest_version_str)
                
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                cache_file.write_text(json.dumps({"last_check": time.time()}))

                if latest_ver > current_ver:
                    console = Console()
                    console.print(f"\n[bold yellow]Notice:[/bold yellow] A new version of Charm is available: [bold red]{current_version_str}[/bold red] -> [bold green]{latest_version_str}[/bold green]")
                    console.print("Run [bold cyan]pip install --upgrade charmos[/bold cyan] to update.\n")
    except Exception:
        pass


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        help="Show the CLI version and exit.",
        callback=version_callback,
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="Enable debug mode with detailed logs and stack traces.",
    ),
):
    """
    Main callback for handling global options like --version and --debug.
    """
    if debug:
        state.DEBUG_MODE = True
        logging.basicConfig(level=logging.DEBUG)
        
    check_for_updates()


if __name__ == "__main__":
    app()
