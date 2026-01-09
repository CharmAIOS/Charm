import asyncio
import json
import os
from typing import Any, Dict, Optional

import typer
from dotenv import dotenv_values, load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

# Import Core Components
from ...core.errors import CharmError
from ...core.loader import CharmLoader

# Try to import Executor (Handle case where 'docker' extra is not installed)
try:
    from ...runner.executor import CharmDockerExecutor

    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False

console = Console()

app = typer.Typer()


async def run_docker_simulation(path: str, payload: Dict[str, Any], env_vars: Dict[str, str]):
    """
    Orchestrates the local Docker simulation using the SDK Executor.
    """
    if not DOCKER_AVAILABLE:
        console.print("[bold red]Error:[/bold red] Docker dependencies not found.")
        console.print("Please install with: [green]pip install 'charmos[runner]'[/green]")
        return

    try:
        import docker

        docker.from_env()
    except Exception:
        console.print("[bold red]Error:[/bold red] Docker engine is not running.")
        console.print("Please start Docker Desktop and try again.")
        return

    executor = CharmDockerExecutor()
    abs_path = os.path.abspath(path)

    console.print(
        Panel(
            f"Mounting: [cyan]{abs_path}[/cyan]\nEnvironment: [cyan]{len(env_vars)} variables[/cyan]",
            title="[bold blue]🚀 Starting Docker Simulation[/bold blue]",
            border_style="blue",
        )
    )

    try:
        async for sse_line in executor.run(
            agent_id="local_sim",
            bundle_url="local_override",  # Signal to use local mount if supported, or pass real URL
            input_payload=payload,
            env_vars=env_vars,
            file_urls={},
            history=[],
            local_source_path=abs_path,  # Mount local path
        ):
            parse_and_print_sse(sse_line)

    except Exception as e:
        console.print(f"[bold red]Docker Execution Error:[/bold red] {e}")


def parse_and_print_sse(sse_line: str):
    """
    Parses Server-Sent Events from the Runner and prints pretty output.
    Format: data: {"type": "...", "content": "..."}
    """
    if not sse_line.startswith("data: "):
        return

    try:
        json_str = sse_line.replace("data: ", "").strip()
        data = json.loads(json_str)
        evt_type = data.get("type")
        content = data.get("content")

        if evt_type == "status":
            console.print(f"[bold green]ℹ️ {content}[/bold green]")

        elif evt_type == "thinking":
            # Strip excessive newlines for cleaner CLI output
            clean_content = str(content).strip()
            if clean_content:
                console.print(f"[dim]{clean_content}[/dim]")

        elif evt_type == "delta":
            # Streaming token (optional: could implement full streaming UI)
            console.print(content, end="")

        elif evt_type == "artifact":
            console.print(f"[cyan]📦 Generated Artifact:[/cyan] {content.get('name')}")

        elif evt_type == "error":
            console.print(f"[bold red]❌ Error:[/bold red] {content}")

        elif evt_type == "final":
            # Same output format as local run
            console.print("\n")
            console.print(
                Panel(Markdown(content), title="Output (Docker Simulation)", border_style="green")
            )

    except Exception:
        pass  # Ignore parse errors for robust stream handling


@app.command("run")
def run_command(
    path: str = typer.Argument(".", help="Path to the Charm project root"),
    input_text: Optional[str] = typer.Option(None, "--input", "-i", help="Simple text input"),
    json_input: Optional[str] = typer.Option(None, "--json", help="Raw JSON input payload"),
    docker: bool = typer.Option(
        False, "--docker", help="Run inside a local Docker container (Simulate Cloud)"
    ),
):
    """
    Run a Charm Agent locally.
    Supports both interactive mode, headless (JSON/Text) mode, and Docker Simulation.
    """
    # 1. Environment Loading
    env_path = os.path.join(path, ".env")
    abs_path = os.path.abspath(env_path)

    # We capture env vars to pass to Docker if needed
    loaded_env_vars: Dict[str, str] = {}

    if os.path.exists(env_path):
        console.print(f"[dim]Loading .env from: {abs_path}[/dim]")
        load_dotenv(env_path, override=True)
        # Read file robustly using dotenv_values
        try:
            raw_env = dotenv_values(env_path)
            loaded_env_vars = {k: v for k, v in raw_env.items() if v is not None}
        except Exception:
            pass

    # 2. Payload Preparation
    payload: Dict[str, Any] = {}
    if json_input:
        try:
            payload = json.loads(json_input)
        except json.JSONDecodeError:
            console.print("[bold red] Error:[/bold red] Invalid JSON format.")
            raise typer.Exit(code=1) from None
    elif input_text:
        payload = {"input": input_text}
    else:
        console.print("[bold yellow]Interactive Mode[/bold yellow] (Press Ctrl+C to exit)")
        user_input = typer.prompt("Enter input")
        payload = {"input": user_input}

    # MODE 1: DOCKER SIMULATION
    if docker:
        # Use asyncio to run the async generator
        asyncio.run(run_docker_simulation(path, payload, loaded_env_vars))
        return

    # MODE 2: LOCAL PYTHON EXECUTION
    try:
        with console.status(
            f"[bold green]Loading Agent from {path}...[/bold green]", spinner="dots"
        ):
            wrapper = CharmLoader.load(path)

        # Assertion to satisfy Mypy
        if not wrapper.config or not wrapper.config.persona or not wrapper.config.runtime:
            raise CharmError("Invalid configuration loaded.")

        console.print(f"[bold green]✔ Loaded Agent:[/bold green] {wrapper.config.persona.name}")

    except CharmError as e:
        console.print(f"[bold red] Load Error:[/bold red] {e}")
        raise typer.Exit(code=1) from e
    except Exception as e:
        console.print(f"[bold red] Unexpected Error:[/bold red] {e}")
        raise typer.Exit(code=1) from e

    try:
        with console.status("[bold blue]Agent is thinking...[/bold blue]", spinner="earth"):
            result = wrapper.invoke(payload)

    except Exception as e:
        console.print(f"[bold red] Execution Error:[/bold red] {e}")
        raise typer.Exit(code=2) from e

    if not json_input:
        console.print("\n")

        if result.get("status") == "success":
            output_content = result.get("output", "")

            console.print(
                Panel(
                    Markdown(str(output_content)),
                    title=f"Output ({wrapper.config.runtime.adapter.type})",
                    border_style="green",
                )
            )
        else:
            error_msg = result.get("message", "Unknown error")
            console.print(
                Panel(f"[bold]Error:[/bold] {error_msg}", title="Agent Failed", border_style="red")
            )
    else:
        console.print("[DEBUG CHECK] Silent Mode Active. Panel suppressed.")
