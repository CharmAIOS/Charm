import typer
import yaml
import json
import httpx
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from ...contracts.uac import CharmConfig
from ..config import get_token, load_config
from ..git import get_repo_info, GitError

console = Console()

def push_command(
    path: str = typer.Argument(".", help="Path to the Charm project root"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview payload without sending"),
    api_base_override: str = typer.Option(None, "--api-base", help="Override API base URL")
):
    """
    Register/Publish the Agent to the Charm Registry.
    Links local metadata with your remote GitHub repository.
    """
    project_path = Path(path).resolve()
    
    token = get_token()
    if not token:
        console.print("[bold red] Auth Error:[/bold red] Not authenticated.")
        console.print("Please run [bold]charm auth[/bold] first.")
        raise typer.Exit(code=1)

    yaml_file = project_path / "charm.yaml"
    if not yaml_file.exists():
        console.print(f"[bold red] Error:[/bold red] charm.yaml not found in {project_path}")
        raise typer.Exit(code=1)

    try:
        with open(yaml_file, "r") as f:
            yaml_data = yaml.safe_load(f)
            config = CharmConfig(**yaml_data)
            uac_payload = config.model_dump(mode='json', exclude_none=True)
    except Exception as e:
        console.print(f"[bold red] Config Error:[/bold red] {e}")
        raise typer.Exit(code=1)

    try:
        repo_info = get_repo_info(project_path)
    except GitError as e:
        console.print(f"[bold red] Git Error:[/bold red] {e}")
        raise typer.Exit(code=1)

    if repo_info["is_dirty"] == "True":
        console.print(Panel(
            "[bold yellow]Warning: Local changes detected![/bold yellow]\n"
            "You have uncommitted or untracked files.\n"
            "The Registry will link to the last commit, which [bold]does not[/bold] include these changes.",
            title="Git Status", border_style="yellow"
        ))
        if not dry_run:
            typer.confirm("Do you want to continue?", abort=True)

    payload = {
        "uac": uac_payload,
        "repo": {
            "url": repo_info["url"],
            "branch": repo_info["branch"],
            "commit": repo_info["commit"]
        }
    }

    if dry_run:
        console.print("\n[bold blue] Dry Run Mode - Payload Preview:[/bold blue]")
        console.print(Syntax(json.dumps(payload, indent=2), "json", theme="monokai", word_wrap=True))
        console.print("\n[dim]No data was sent to the server.[/dim]")
        raise typer.Exit(code=0)

    config_data = load_config()
    api_base = api_base_override or config_data["core"]["api_base"]
    api_base = api_base.rstrip("/")
    target_url = f"{api_base}/v1/agents"

    console.print(f" Pushing to [underline]{target_url}[/underline]...")

    try:
        with console.status("[bold green]Uploading Metadata...[/bold green]"):
            response = httpx.post(
                target_url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                },
                timeout=10.0
            )

        if response.status_code in [200, 201]:
            data = response.json()
            agent_url = data.get("url", "https://charm.ai/store")
            
            console.print(Panel(
                f"[bold]Agent:[/bold] {config.persona.name}\n"
                f"[bold]Version:[/bold] {config.version}\n"
                f"[bold]ID:[/bold] {data.get('agent_id', 'N/A')}\n\n"
                f"🔗 [link={agent_url}]{agent_url}[/link]",
                title="[bold green]✔ Successfully Published[/bold green]",
                border_style="green"
            ))
        else:
            console.print(f"[bold red] Server Error ({response.status_code}):[/bold red]")
            console.print(response.text)
            raise typer.Exit(code=1)

    except httpx.RequestError as e:
        console.print(f"[bold red] Connection Error:[/bold red] Could not connect to Registry.")
        console.print(f"Details: {e}")
        raise typer.Exit(code=1)