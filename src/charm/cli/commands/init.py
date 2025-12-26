import shutil
from importlib.resources import files
from pathlib import Path

import typer
from rich.console import Console

app = typer.Typer(help="Initialize a new Charm agent")
console = Console()


@app.command("init")
def init_command(
    name: str = typer.Argument(..., help="Name of the agent directory"),
    template: str = typer.Option("default", help="Template to use"),
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
        # Load the default template from the package resources.
        template_source = files("charm.templates").joinpath("charm.default.yaml")
        content = template_source.read_text(encoding="utf-8")

        # Write charm.yaml
        target_file = project_path / "charm.yaml"
        target_file.write_text(content, encoding="utf-8")

        # Create src/main.py placeholder
        (project_path / "src").mkdir()
        (project_path / "src" / "main.py").write_text("# Your agent code here\n", encoding="utf-8")

        console.print(f"[bold green]✔ Created new agent project: {name}[/bold green]")
        console.print("  ├── charm.yaml (Created from template)")
        console.print("  └── src/main.py")
        console.print("\nNext step:\n  [cyan]cd[/cyan] " + name + "\n  [cyan]charm validate[/cyan]")

    except Exception as e:
        console.print(f"[bold red]Error loading template:[/bold red] {e}")
        shutil.rmtree(project_path)  # Cleanup on failure
        raise typer.Exit(1) from e
