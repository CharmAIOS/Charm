import typer
import json
import os
from typing import Optional
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax

from ...core.loader import CharmLoader
from ...core.errors import CharmError

console = Console()

def run_command(
    path: str = typer.Argument(".", help="Path to the Charm project root"),
    input_text: Optional[str] = typer.Option(None, "--input", "-i", help="Simple text input"),
    json_input: Optional[str] = typer.Option(None, "--json", help="Raw JSON input payload"),
):
    """
    Run a Charm Agent locally.
    """
    payload = {}
    
    if json_input:
        try:
            payload = json.loads(json_input)
        except json.JSONDecodeError:
            console.print("[bold red] Error:[/bold red] Invalid JSON format.")
            raise typer.Exit(code=1)
    elif input_text:
        payload = {"input": input_text}
    else:
        console.print("[bold yellow]Interactive Mode[/bold yellow] (Press Ctrl+C to exit)")
        user_input = typer.prompt("Enter input")
        payload = {"input": user_input}

    try:
        with console.status(f"[bold green]Loading Agent from {path}...[/bold green]", spinner="dots"):
            wrapper = CharmLoader.load(path)
            
        console.print(f"[bold green]✔ Loaded Agent:[/bold green] {wrapper.config.persona.name}")
        
    except CharmError as e:
        console.print(f"[bold red] Load Error:[/bold red] {e}")
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[bold red] Unexpected Error:[/bold red] {e}")
        raise typer.Exit(code=1)

    try:
        with console.status("[bold blue]Agent is thinking...[/bold blue]", spinner="earth"):
            result = wrapper.invoke(payload)
            
    except Exception as e:
        console.print(f"[bold red] Execution Error:[/bold red] {e}")
        raise typer.Exit(code=2)

    console.print("\n")
    
    if result.get("status") == "success":
        output_content = result.get("output", "")
        
        console.print(Panel(
            Markdown(output_content),
            title=f"✨ Output ({wrapper.config.runtime.adapter.type})",
            border_style="green"
        ))
    else:
        console.print(Panel(
            str(result),
            title="Agent Failed",
            border_style="red"
        ))