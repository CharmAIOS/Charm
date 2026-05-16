import json
import shutil
import urllib.request
from pathlib import Path
from typing import Optional, Dict, Any, List

import typer
from rich.console import Console
from rich.prompt import Prompt

app = typer.Typer(help="Initialize a new Charm agent")
console = Console()

MANIFEST_URL = "https://raw.githubusercontent.com/charmaios/charm/main/templates-manifest.json"

def fetch_manifest() -> Dict[str, Any]:
    try:
        with urllib.request.urlopen(MANIFEST_URL, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as e:
        console.print(f"[bold yellow]Warning:[/bold yellow] Failed to fetch community templates: {e}")
        console.print("Using fallback offline template...")
        return {
            "templates": [
                {
                    "id": "python",
                    "description": "Fallback Python template (offline mode)",
                    "files": [
                        {
                            "path": "charm.yaml",
                            "content": "persona:\n  name: \"my-agent\"\n  description: \"A Charm agent\"\nruntime:\n  adapter:\n    type: python\n    entry_point: src.main:agent\n"
                        },
                        {
                            "path": ".charmignore",
                            "content": ".env\n__pycache__/\n*.pyc\n"
                        },
                        {
                            "path": "src/__init__.py",
                            "content": ""
                        },
                        {
                            "path": "src/main.py",
                            "content": "# Define your agent logic here.\n# The object must be named 'agent' to match charm.yaml entry_point.\n\ndef agent(inputs):\n    return f\"Hello from Charm! Input received: {inputs}\"\n"
                        }
                    ],
                    "post_init_message": "  ├── charm.yaml\n  ├── .charmignore\n  └── src/\n      ├── __init__.py\n      └── main.py"
                }
            ]
        }


@app.command("init")
def init_command(
    name: str = typer.Argument(
        ...,
        help="Agent directory path (e.g. '.' for current directory, 'my-agent' for new folder)",
    ),
    template: str = typer.Option(
        "python",
        help="Template to use (fetched dynamically from community registry)."
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
    manifest = fetch_manifest()
    templates = manifest.get("templates", [])
    
    if interactive:
        run_interactive(project_path, templates)
        return

    if create:
        create_single_file(project_path, create, templates)
        return

    create_project(project_path, template, templates)


def run_interactive(project_path: Path, templates: List[Dict[str, Any]]):
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
        console.print("\n[bold]Available templates:[/bold]")
        valid_ids = []
        for t in templates:
            t_id = t["id"]
            desc = t.get("description", "")
            console.print(f"  [cyan]{t_id:<26}[/cyan] {desc}")
            valid_ids.append(t_id)
        console.print()

        template_choice = Prompt.ask(
            "[bold]Select template[/bold]",
            choices=valid_ids,
            default="python" if "python" in valid_ids else valid_ids[0],
        )

        agent_name = Prompt.ask(
            "[bold]Agent name[/bold]",
            default=project_path.name if project_path.name != "." else "my-agent",
        )

        description = Prompt.ask(
            "[bold]Description[/bold]",
            default="A Charm agent",
        )

        create_project_from_template(project_path, template_choice, templates, agent_name, description)

        console.print("\n[bold green]✔ Project created successfully![/bold green]")
        console.print(f"\nNext step:\n  [cyan]cd[/cyan] {project_path}\n  [cyan]charm push[/cyan]")

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        if project_path.exists():
            shutil.rmtree(project_path)
        raise typer.Exit(1) from e


def create_single_file(project_path: Path, create: str, templates: List[Dict[str, Any]]):
    if not project_path.exists():
        project_path.mkdir(parents=True)

    target_file = project_path / create
    if target_file.exists():
        console.print(f"[bold red]Error:[/bold red] File '{target_file}' already exists.")
        raise typer.Exit(1)

    try:
        # Use python template for single file creation
        python_tpl = next((t for t in templates if t["id"] == "python"), templates[0])
        file_tpl = next((f for f in python_tpl["files"] if f["path"] == "charm.yaml"), None)
        if not file_tpl:
            console.print(f"[bold red]Error:[/bold red] Template does not contain charm.yaml")
            raise typer.Exit(1)
            
        target_file.write_text(file_tpl["content"], encoding="utf-8")
        console.print(f"[bold green]✔ Created file: {target_file}[/bold green]")
    except Exception as e:
        console.print(f"[bold red]Error creating file:[/bold red] {e}")
        raise typer.Exit(1) from e


def create_project(project_path: Path, template: str, templates: List[Dict[str, Any]]):
    valid_ids = [t["id"] for t in templates]
    if template not in valid_ids:
        console.print(f"[bold red]Error:[/bold red] Invalid template '{template}'. Valid options: {', '.join(valid_ids)}")
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
        create_project_from_template(project_path, template, templates)
        console.print("\nNext step:\n  [cyan]cd[/cyan] " + str(project_path) + "\n  [cyan]charm push[/cyan]")
    except Exception as e:
        console.print(f"[bold red]Error loading template:[/bold red] {e}")
        if project_path.exists():
            shutil.rmtree(project_path)
        raise typer.Exit(1) from e


def create_project_from_template(
    project_path: Path,
    template: str,
    templates: List[Dict[str, Any]],
    name: Optional[str] = None,
    description: Optional[str] = None,
):
    import re
    tpl_data = next((t for t in templates if t["id"] == template), None)
    if not tpl_data:
        raise Exception(f"Template '{template}' not found in manifest.")
        
    for file_obj in tpl_data.get("files", []):
        file_path = project_path / file_obj["path"]
        content = file_obj["content"]
        
        # Customize charm.yaml if name/desc provided
        if file_obj["path"] == "charm.yaml":
            if name:
                content = re.sub(r'name: "[^"]*"', f'name: "{name}"', content)
            if description:
                content = re.sub(r'description: "[^"]*"', f'description: "{description}"', content)
                
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        
    console.print(f"[bold green]✔ Created {tpl_data.get('id', 'Agent')} project: {project_path.name}[/bold green]")
    post_msg = tpl_data.get("post_init_message", "")
    if post_msg:
        console.print(post_msg)
