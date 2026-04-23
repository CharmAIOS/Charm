import httpx
import typer
import yaml
from pathlib import Path
from datetime import datetime
from rich.console import Console
from rich.table import Table

from ..config import get_token, load_config
from .. import state

console = Console()
app = typer.Typer()

DEFAULT_API_BASE = "https://store.charmos.io/api"

@app.callback(invoke_without_command=True)
def logs_command(
    path: str = typer.Option(".", "--path", help="Path to the Charm project root"),
    limit: int = typer.Option(50, "--limit", "-l", help="Number of logs to fetch (max 500)"),
    api_base_override: str = typer.Option(None, "--api-base", help="Override API base URL"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug mode"),
):
    if debug:
        state.DEBUG_MODE = True
    """
    Fetch remote execution logs for the current agent.
    """
    project_path = Path(path).resolve()
    
    token = get_token()
    if not token:
        console.print("[bold red]Auth Error:[/bold red] Please run [bold]charm auth[/bold] first to read secure logs.")
        raise typer.Exit(code=1)

    yaml_file = project_path / "charm.yaml"
    if not yaml_file.exists():
        console.print(f"[bold red]Error:[/bold red] charm.yaml not found in {project_path}. Cannot resolve agent identity for logs.")
        raise typer.Exit(code=1)

    try:
        with open(yaml_file, "r") as f:
            uac_raw = yaml.safe_load(f)
            
        agent_id = uac_raw.get("id")
        if not agent_id:
            console.print("[bold red]Error:[/bold red] Agent has no ID. Please 'charm push' at least once to register the agent.")
            raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[bold red]Config Error:[/bold red] {e}")
        raise typer.Exit(code=1)

    config_data = load_config()
    api_base = api_base_override or config_data.get("core", {}).get("api_base") or DEFAULT_API_BASE
    api_base = str(api_base).rstrip("/")

    headers = {"Authorization": f"Bearer {token}"}

    with console.status("[bold green]Fetching execution traces from Cloud Runner...[/bold green]"):
        try:
            resp = httpx.get(
                f"{api_base}/v1/agents/logs?agent_id={agent_id}&limit={limit}",
                headers=headers,
                timeout=15.0
            )

            if resp.status_code != 200:
                console.print(f"[bold red]Failed to fetch logs ({resp.status_code}):[/bold red]")
                try:
                    console.print(resp.json().get("error", resp.text))
                except Exception:
                    console.print(resp.text)
                
                if state.DEBUG_MODE:
                    console.print("[dim]Debug Trace:[/dim]")
                    console.print(resp.text)
                    
                raise typer.Exit(code=1)

            data = resp.json()
            logs = data.get("logs", [])

        except Exception as e:
            console.print(f"[bold red]Connection Error:[/bold red] {e}")
            if state.DEBUG_MODE:
                console.print_exception()
            raise typer.Exit(code=1)

    if not logs:
        console.print("[dim]No historical run logs found for this agent.[/dim]")
        return

    table = Table(title="Remote Execution Logs", show_header=True, header_style="bold magenta")
    table.add_column("Time", style="dim", width=20)
    table.add_column("Type", style="cyan", width=12)
    table.add_column("Details")

    for log in logs:
        # Endpoint returns: created_at, status, input_payload, error_message
        ts_raw = log.get("created_at", "")
        try:
            dt = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            ts = dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            ts = ts_raw[:19] if ts_raw else "N/A"

        status = log.get("status", "unknown")
        error_msg = log.get("error_message", "")
        input_payload = log.get("input_payload", {})

        # Determine styling based on status
        type_style = "cyan"
        if status == "error":
            type_style = "bold red"
        elif status == "success":
            type_style = "bold green"
        elif status == "running":
            type_style = "bold yellow"

        detail_text = ""
        if error_msg:
            detail_text = error_msg[:100] + "..." if len(str(error_msg)) > 100 else str(error_msg)
        elif input_payload:
            msg = input_payload.get("message", str(input_payload))
            detail_text = msg[:100] + "..." if len(msg) > 100 else msg

        table.add_row(ts, f"[{type_style}]{status}[/{type_style}]", detail_text)

    console.print(table)
    console.print(f"\n[dim]Showing last {len(logs)} execution events.[/dim]")
