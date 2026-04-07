import shutil
from importlib.resources import files
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

app = typer.Typer(help="Initialize a new Charm agent")
console = Console()

# Valid templates
VALID_TEMPLATES = ["python", "openclaw"]


@app.command("init")
def init_command(
    name: str = typer.Argument(
        ...,
        help="Agent directory path (e.g. '.' for current directory, 'my-agent' for new folder)",
    ),
    template: str = typer.Option(
        "python", help="Template to use: 'python' (Python Code) or 'openclaw' (MCP Agent)"
    ),
    create: Optional[str] = typer.Option(
        None, "--create", help="Specifically create a single file from template (e.g. 'charm.yaml')"
    ),
    interactive: bool = typer.Option(
        False, "--interactive", "-i", help="Run in interactive mode with prompts"
    ),
):
    """
    Scaffold a new Charm Agent project.
    """
    project_path = Path(name)

    # Interactive mode
    if interactive:
        run_interactive(project_path)
        return

    # Single file creation mode
    if create:
        create_single_file(project_path, create)
        return

    # Full project creation
    create_project(project_path, template)


def run_interactive(project_path: Path):
    """Run init in interactive mode with prompts."""
    from rich.prompt import Prompt, Confirm

    # Check if directory exists
    if project_path.exists():
        if not project_path.is_dir():
            console.print(f"[bold red]Error:[/bold red] '{project_path}' exists and is not a directory.")
            raise typer.Exit(1)
        if any(project_path.iterdir()):
            console.print(f"[bold red]Error:[/bold red] Directory '{project_path}' already exists and is not empty.")
            raise typer.Exit(1)
    else:
        project_path.mkdir(parents=True)

    try:
        # Prompt for template
        template_choice = Prompt.ask(
            "[bold]Select template[/bold]",
            choices=VALID_TEMPLATES,
            default="python",
        )

        # Prompt for agent name (optional, can use directory name)
        agent_name = Prompt.ask(
            "[bold]Agent name[/bold]",
            default=project_path.name if project_path.name != "." else "my-agent",
        )

        # Prompt for description
        description = Prompt.ask(
            "[bold]Description[/bold]",
            default="A Charm agent",
        )

        # Create the project with selected template
        create_project_from_template(project_path, template_choice, agent_name, description)

        console.print("\n[bold green]✔ Project created successfully![/bold green]")
        console.print(f"\nNext step:\n  [cyan]cd[/cyan] {project_path}\n  [cyan]charm push[/cyan]")

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        if project_path.exists():
            shutil.rmtree(project_path)
        raise typer.Exit(1)


def create_single_file(project_path: Path, create: str):
    """Create a single file from template."""
    if not project_path.exists():
        project_path.mkdir(parents=True)

    target_file = project_path / create
    if target_file.exists():
        console.print(f"[bold red]Error:[/bold red] File '{target_file}' already exists.")
        raise typer.Exit(1)

    try:
        # Use python template for single file creation
        template_source = files("charm.templates").joinpath("python.yaml")
        yaml_content = template_source.read_text(encoding="utf-8")
        target_file.write_text(yaml_content, encoding="utf-8")
        console.print(f"[bold green]✔ Created file: {target_file}[/bold green]")
    except Exception as e:
        console.print(f"[bold red]Error creating file:[/bold red] {e}")
        raise typer.Exit(1) from e


def create_project(project_path: Path, template: str):
    """Create a full project from template."""
    # Validate template
    if template not in VALID_TEMPLATES:
        console.print(f"[bold red]Error:[/bold red] Invalid template '{template}'. Valid options: {', '.join(VALID_TEMPLATES)}")
        raise typer.Exit(1)

    if project_path.exists():
        if not project_path.is_dir():
            console.print(f"[bold red]Error:[/bold red] '{project_path}' already exists and is not a directory.")
            raise typer.Exit(1)
        if any(project_path.iterdir()):
            console.print(f"[bold red]Error:[/bold red] Directory '{project_path}' already exists and is not empty.")
            raise typer.Exit(1)
    else:
        project_path.mkdir(parents=True)

    try:
        create_project_from_template(project_path, template)
        console.print("\nNext step:\n  [cyan]cd[/cyan] " + str(project_path) + "\n  [cyan]charm push[/cyan]")
    except Exception as e:
        console.print(f"[bold red]Error loading template:[/bold red] {e}")
        if project_path.exists():
            shutil.rmtree(project_path)
        raise typer.Exit(1) from e


def create_project_from_template(project_path: Path, template: str, name: str = None, description: str = None):
    """Create project from template with optional customization."""
    # Load template YAML
    template_source = files("charm.templates").joinpath(f"{template}.yaml")
    yaml_content = template_source.read_text(encoding="utf-8")

    # Customize name and description if provided
    if name or description:
        import re
        if name:
            yaml_content = re.sub(r'name: "[^"]*"', f'name: "{name}"', yaml_content)
        if description:
            yaml_content = re.sub(r'description: "[^"]*"', f'description: "{description}"', yaml_content)

    # Write charm.yaml
    (project_path / "charm.yaml").write_text(yaml_content, encoding="utf-8")

    # Create .charmignore from template (consistent for all templates)
    ignore_source = files("charm.templates").joinpath("charm.ignore.template")
    ignore_content = ignore_source.read_text(encoding="utf-8")
    (project_path / ".charmignore").write_text(ignore_content, encoding="utf-8")

    if template == "python":
        # Create src directory with main.py
        (project_path / "src").mkdir(exist_ok=True)
        (project_path / "src" / "main.py").write_text(
            "# Define your agent logic here.\n"
            "# The object must be named 'agent' to match charm.yaml entry_point.\n\n"
            "def agent(inputs):\n"
            '    return f"Hello from Charm! Input received: {inputs}"\n',
            encoding="utf-8",
        )
        console.print(f"[bold green]✔ Created Python Agent project: {project_path.name}[/bold green]")
        console.print("  ├── charm.yaml")
        console.print("  ├── .charmignore")
        console.print("  └── src/main.py")

    elif template == "openclaw":
        # Create skills directory
        skills_dir = project_path / "skills"
        skills_dir.mkdir(exist_ok=True)

        # Create sample custom skill
        sample_skill = skills_dir / "my_tool"
        sample_skill.mkdir(exist_ok=True)
        (sample_skill / "server.py").write_text(
            "print('Hello from custom skill!')\n# Implement MCP server here",
            encoding="utf-8",
        )
        (sample_skill / "requirements.txt").write_text("mcp", encoding="utf-8")

        console.print(f"[bold green]✔ Created OpenClaw Agent project: {project_path.name}[/bold green]")
        console.print("  ├── charm.yaml")
        console.print("  ├── .charmignore")
        console.print("  └── skills/")
        console.print("      └── my_tool/  <-- Example custom skill")
