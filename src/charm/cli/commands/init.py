import shutil
from importlib.resources import files
from pathlib import Path

import typer
from rich.console import Console

app = typer.Typer(help="Initialize a new Charm agent")
console = Console()


@app.command("init")
def init_command(
    name: str = typer.Argument(
        ...,
        help="Agent directory path (e.g. 'my-agent' or 'agents/my-agent' to keep under agents/)",
    ),
    template: str = typer.Option(
        "default", help="Template to use: 'default' (Python Code) or 'openclaw' (MCP Agent)"
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

        if template == "skill" or template == "openclaw":
            # [NEW] OpenClaw Template
            yaml_content = """version: "0.4.1"

persona:
  name: "My OpenClaw Agent"
  description: "A persistent, stateful agent."
  version: "0.1.0"
  authors: ["You"]
  tags: ["assistant"]

interface:
  input:
    properties:
      input: { type: "string", title: "Instruction", x-ui-widget: "textarea" }
  output:
    type: "string"

runtime:
  adapter:
    type: "openclaw"
  
  # The Brain Configuration
  config:
    model: "gpt-4o"
    temperature: 0.5
    # This becomes your agent's long-term identity
    system_prompt: |
      You are a helpful assistant living in the cloud.
      You have access to a persistent workspace.
      Always check your memory file before answering.

  mode: "full" # Required for OpenClaw

  skills:
    # 1. Official Skill (Registry)
    - name: "google-search"
      source: "smithery:@mcp/google-search"

    # 2. Local Custom Skill (Folder)
    # - name: "my-tool"
    #   source: "local:./skills/my_tool"
"""
            # Write YAML
            (project_path / "charm.yaml").write_text(yaml_content, encoding="utf-8")

            # Create .charmignore
            ignore_content = ".env\n__pycache__\nnode_modules\n.git\n"
            (project_path / ".charmignore").write_text(ignore_content, encoding="utf-8")

            # Create Skills Directory Structure
            skills_dir = project_path / "skills"
            skills_dir.mkdir(exist_ok=True)

            # Create a sample custom skill
            sample_skill = skills_dir / "my_tool"
            sample_skill.mkdir(exist_ok=True)

            (sample_skill / "server.py").write_text(
                "print('Hello from custom skill!')\n# Implement MCP server here", encoding="utf-8"
            )
            (sample_skill / "requirements.txt").write_text("mcp", encoding="utf-8")

            console.print(f"[bold green]✔ Created OpenClaw Agent: {name}[/bold green]")
            console.print("  ├── charm.yaml")
            console.print("  └── skills/       <-- Place custom Python/Node skills here")
            console.print("      └── my_tool/  <-- Example")

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
