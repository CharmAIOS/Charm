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
    template: str = typer.Option(
        "default", help="Template to use: 'default' (Python Code) or 'skill' (OpenClaw)"
    ),
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
        # Load the base template content
        template_source = files("charm.templates").joinpath("charm.default.yaml")
        yaml_content = template_source.read_text(encoding="utf-8")

        # Customize based on template type
        # Create .charmignore
        ignore_source = files("charm.templates").joinpath("charm.ignore.template")
        ignore_content = ignore_source.read_text(encoding="utf-8")

        ignore_target = project_path / ".charmignore"
        ignore_target.write_text(ignore_content, encoding="utf-8")

        if template == "skill":
            # Modify YAML for Skill/OpenClaw mode
            # Replace default 'crewai' adapter with 'openclaw' and remove entry_point hints
            yaml_content = yaml_content.replace('type: "crewai"', 'type: "openclaw"')
            yaml_content = yaml_content.replace(
                'entry_point: "src.main:agent"', "# entry_point: (Not needed for OpenClaw)"
            )

            # Uncomment the skills section example for better DX
            yaml_content = yaml_content.replace("# skills:", "skills:")
            yaml_content = yaml_content.replace(
                '#   - name: "google-search"', '  - name: "google-search"'
            )
            yaml_content = yaml_content.replace(
                '#     source: "smithery:@mcp/google-search"',
                '    source: "smithery:@mcp/google-search"',
            )

            # Write charm.yaml
            target_file = project_path / "charm.yaml"
            target_file.write_text(yaml_content, encoding="utf-8")

            console.print(f"[bold green]✔ Created new Skill Agent project: {name}[/bold green]")
            console.print("  ├── charm.yaml (OpenClaw Configuration)")
            console.print("  └── .charmignore")

        else:
            # 2. Default (Code-based) mode
            # Write standard charm.yaml
            target_file = project_path / "charm.yaml"
            target_file.write_text(yaml_content, encoding="utf-8")

            # Create src/main.py placeholder
            (project_path / "src").mkdir()
            (project_path / "src" / "main.py").write_text(
                "# Define your agent logic here.\n"
                "# The object must be named 'agent' to match charm.yaml entry_point.\n\n"
                "def agent(inputs):\n"
                '    return f"Hello from Charm! Input received: {inputs}"\n',
                encoding="utf-8",
            )

            console.print(f"[bold green]✔ Created new Code Agent project: {name}[/bold green]")
            console.print("  ├── charm.yaml")
            console.print("  ├── .charmignore")
            console.print("  └── src/main.py")

        console.print("\nNext step:\n  [cyan]cd[/cyan] " + name + "\n  [cyan]charm push[/cyan]")

    except Exception as e:
        console.print(f"[bold red]Error loading template:[/bold red] {e}")
        shutil.rmtree(project_path)  # Cleanup on failure
        raise typer.Exit(1) from e
