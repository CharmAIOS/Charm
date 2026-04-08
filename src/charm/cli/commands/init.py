import shutil
from importlib.resources import files
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

app = typer.Typer(help="Initialize a new Charm agent")
console = Console()

# Valid templates
VALID_TEMPLATES = [
    "python",
    "openclaw",
    "research-agent",
    "code-review-agent",
    "customer-support-agent",
    "data-pipeline-agent",
    "slack-bot",
]

_TEMPLATE_DESCRIPTIONS = {
    "python":                 "Custom Python agent (code-based)",
    "openclaw":               "MCP-powered OpenClaw agent",
    "research-agent":         "Web research & report generation",
    "code-review-agent":      "Code review for bugs, security, style",
    "customer-support-agent": "Always-on customer support daemon",
    "data-pipeline-agent":    "Data processing & ETL pipeline",
    "slack-bot":              "Persistent Slack workspace bot",
}


@app.command("init")
def init_command(
    name: str = typer.Argument(
        ...,
        help="Agent directory path (e.g. '.' for current directory, 'my-agent' for new folder)",
    ),
    template: str = typer.Option(
        "python",
        help=(
            "Template to use. Options: "
            + ", ".join(f"'{t}'" for t in VALID_TEMPLATES)
        ),
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
        # Show template menu
        console.print("\n[bold]Available templates:[/bold]")
        for t, desc in _TEMPLATE_DESCRIPTIONS.items():
            console.print(f"  [cyan]{t:<26}[/cyan] {desc}")
        console.print()

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

    elif template == "research-agent":
        # OpenClaw-based — no extra source files needed (system_prompt drives it)
        console.print(f"[bold green]✔ Created Research Agent project: {project_path.name}[/bold green]")
        console.print("  ├── charm.yaml  ← system_prompt & web-search skill pre-configured")
        console.print("  └── .charmignore")
        console.print("\n[dim]Next:[/dim] edit [cyan]charm.yaml[/cyan] to refine the system_prompt, then [cyan]charm push[/cyan]")

    elif template == "code-review-agent":
        # Custom Python adapter — scaffold src/main.py with a starter reviewer
        (project_path / "src").mkdir(exist_ok=True)
        (project_path / "src" / "main.py").write_text(
            "# Code Review Agent\n"
            "# Receives code + focus area, returns a structured review.\n\n"
            "def agent(inputs):\n"
            "    code = inputs.get('code', '')\n"
            "    language = inputs.get('language', 'auto-detect') or 'auto-detect'\n"
            "    focus = inputs.get('focus', 'general')\n\n"
            "    # TODO: call your preferred LLM here\n"
            "    # Example (pseudo-code):\n"
            "    # prompt = build_review_prompt(code, language, focus)\n"
            "    # return llm.complete(prompt)\n\n"
            "    return f'[Code Review — {focus}]\\n\\nLanguage: {language}\\n\\n{code[:80]}...\\n\\n(Implement your review logic above)'\n",
            encoding="utf-8",
        )
        console.print(f"[bold green]✔ Created Code Review Agent project: {project_path.name}[/bold green]")
        console.print("  ├── charm.yaml")
        console.print("  ├── .charmignore")
        console.print("  └── src/main.py  ← add your LLM call here")

    elif template == "customer-support-agent":
        # OpenClaw daemon — system_prompt drives the support behaviour
        console.print(f"[bold green]✔ Created Customer Support Agent project: {project_path.name}[/bold green]")
        console.print("  ├── charm.yaml  ← daemon lifecycle, knowledge-base skill pre-configured")
        console.print("  └── .charmignore")
        console.print("\n[dim]Tip:[/dim] this agent runs as a [bold]daemon[/bold] — it stays alive between requests.")
        console.print("Edit the system_prompt in [cyan]charm.yaml[/cyan] with your product knowledge, then [cyan]charm push[/cyan]")

    elif template == "data-pipeline-agent":
        # Custom Python adapter — scaffold src/main.py with input routing
        (project_path / "src").mkdir(exist_ok=True)
        (project_path / "src" / "main.py").write_text(
            "# Data Pipeline Agent\n"
            "# Routes data through clean / summarise / transform / analyse tasks.\n\n"
            "def agent(inputs):\n"
            "    data = inputs.get('data', '')\n"
            "    task = inputs.get('task', 'analyse')\n"
            "    output_format = inputs.get('output_format', 'markdown')\n\n"
            "    # TODO: implement each task branch\n"
            "    if task == 'clean':\n"
            "        result = data.strip()  # replace with real cleaning logic\n"
            "    elif task == 'summarise':\n"
            "        result = data[:200] + '...'  # replace with LLM summarisation\n"
            "    elif task == 'transform':\n"
            "        result = data  # replace with transformation logic\n"
            "    else:  # analyse\n"
            "        result = f'Analysis of {len(data)} chars of data.'  # replace with LLM analysis\n\n"
            "    if output_format == 'json':\n"
            "        import json\n"
            "        return json.dumps({'result': result})\n"
            "    return result\n",
            encoding="utf-8",
        )
        console.print(f"[bold green]✔ Created Data Pipeline Agent project: {project_path.name}[/bold green]")
        console.print("  ├── charm.yaml")
        console.print("  ├── .charmignore")
        console.print("  └── src/main.py  ← implement your pipeline tasks here")

    elif template == "slack-bot":
        # OpenClaw daemon with Slack MCP skill
        console.print(f"[bold green]✔ Created Slack Bot Agent project: {project_path.name}[/bold green]")
        console.print("  ├── charm.yaml  ← daemon lifecycle, Slack MCP skill pre-configured")
        console.print("  └── .charmignore")
        console.print("\n[dim]Tip:[/dim] this agent runs as a [bold]daemon[/bold] — it persists across Slack events.")
        console.print("Add your Slack API credentials as secrets, then [cyan]charm push[/cyan]")
