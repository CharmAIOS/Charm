import typer
import shutil
import os
from pathlib import Path
from rich.console import Console
from importlib.resources import files 

app = typer.Typer(help="Initialize a new Charm agent")
console = Console()

@app.command("init")
def init_command(
    name: str = typer.Argument(..., help="Name of the agent directory"),
    template: str = typer.Option("default", help="Template to use")
):
    """
    Scaffold a new Charm Agent project.
    """
    project_path = Path(name)
    
    if project_path.exists():
        console.print(f"[bold red]Error:[/bold red] Directory '{name}' already exists.")
        raise typer.Exit(1)

    project_path.mkdir(parents=True)
    
    try:
        template_source = files("charm.templates").joinpath("charm.default.yaml")
        
        content = template_source.read_text(encoding="utf-8")
        
        target_file = project_path / "charm.yaml"
        target_file.write_text(content, encoding="utf-8")
        
        (project_path / "src").mkdir()
        (project_path / "src" / "main.py").write_text("# Your agent code here\n", encoding="utf-8")

        console.print(f"[bold green]✔ Created new agent project: {name}[/bold green]")
        console.print(f"  ├── charm.yaml (Created from template)")
        console.print(f"  └── src/main.py")
        console.print("\nNext step:\n  [cyan]cd[/cyan] " + name + "\n  [cyan]charm validate[/cyan]")

    except Exception as e:
        console.print(f"[bold red]Error loading template:[/bold red] {e}")
        shutil.rmtree(project_path)
        raise typer.Exit(1)