import typer
import yaml
import os
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from pydantic import ValidationError

from ...contracts.uac import CharmConfig

console = Console()

def validate_command(
    path: str = typer.Argument(".", help="Path to the Charm project root")
):
    """
    Validate the charm.yaml configuration file against UAC standards.
    """
    project_path = Path(path).resolve()
    yaml_file = project_path / "charm.yaml"

    if not yaml_file.exists():
        console.print(f"[bold red] Error:[/bold red] charm.yaml not found in {project_path}")
        console.print("Are you in the right directory?")
        raise typer.Exit(code=2)

    try:
        with open(yaml_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception as e:
        console.print(f"[bold red] YAML Parse Error:[/bold red] {e}")
        raise typer.Exit(code=1)

    try:
        config = CharmConfig(**data)
        
        info_text = (
            f"[bold]Name:[/bold] {config.persona.name}\n"
            f"[bold]Agent Version:[/bold] {config.persona.version}\n"  
            f"[bold]UAC Spec:[/bold] {config.version}\n"             
            f"[bold]Adapter:[/bold] {config.runtime.adapter.type}\n"
            f"[bold]Entry Point:[/bold] {config.runtime.adapter.entry_point}"
        )
        
        console.print(Panel(
            info_text,
            title="[bold green]✔ charm.yaml is Valid (UAC v0.4.1)[/bold green]",
            border_style="green",
            expand=False
        ))
        
    except ValidationError as e:
        console.print("[bold red]✖ Validation Failed:[/bold red]")
        for err in e.errors():
            loc = " -> ".join(str(x) for x in err['loc'])
            msg = err['msg']
            console.print(f"  - [bold yellow]{loc}[/bold yellow]: {msg}")
        raise typer.Exit(code=1)