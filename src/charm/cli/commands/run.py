import asyncio
import json
import os
import time
from typing import Any, Dict, List, Optional

import typer
from dotenv import dotenv_values, load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

# Import Core Components
from ...core.errors import CharmError
from ...core.loader import CharmLoader
from .. import state

# Try to import Executor (Handle case where 'docker' extra is not installed)
try:
    from ...runner.executor import CharmDockerExecutor

    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False

console = Console()

app = typer.Typer()

# Valid adapter types
def get_valid_adapter_types() -> List[str]:
    from importlib.metadata import entry_points
    try:
        eps = entry_points(group="charm.adapters")
        return [ep.name for ep in eps]
    except Exception:
        return ["python", "crewai", "langchain", "langgraph", "openclaw", "node", "custom"]

VALID_ADAPTER_TYPES = get_valid_adapter_types()


async def run_docker_simulation(
    path: str,
    payload: Dict[str, Any],
    env_vars: Dict[str, str],
    mock_oauth: bool = False,
    mock_skills: bool = False,
):
    """
    Orchestrates the local Docker simulation using the SDK Executor.
    """
    if not DOCKER_AVAILABLE:
        console.print("[bold red]Error:[/bold red] Docker dependencies not found.")
        console.print("Please install with: [green]pip install 'charmos[runner]'[/green]")
        return

    try:
        import docker as _docker

        _docker.from_env()  # type: ignore[attr-defined]
    except Exception:
        console.print("[bold red]Error:[/bold red] Docker engine is not running.")
        console.print("Please start Docker Desktop and try again.")
        return

    executor = CharmDockerExecutor()
    abs_path = os.path.abspath(path)

    # Detect adapter type and skills from charm.yaml for image selection
    adapter_type = "custom"
    skills = []
    runtime_mode = "standard"
    lifecycle = "serverless"
    custom_image = None
    try:
        import yaml

        charm_yaml_path = os.path.join(abs_path, "charm.yaml")
        if os.path.exists(charm_yaml_path):
            with open(charm_yaml_path, "r") as f:
                uac = yaml.safe_load(f)
            runtime = uac.get("runtime", {})
            adapter_cfg = runtime.get("adapter", {})
            adapter_type = adapter_cfg.get("type", "custom")
            skills = runtime.get("skills", [])
            runtime_mode = runtime.get("mode", "standard")
            lifecycle = runtime.get("lifecycle", "serverless")
            custom_image = runtime.get("custom_image")
    except Exception:
        pass

    # Validate adapter type
    if adapter_type not in VALID_ADAPTER_TYPES:
        console.print(f"[bold red]Warning:[/bold red] Unknown adapter type '{adapter_type}'. Using 'custom'.")
        adapter_type = "custom"

    # Select correct Docker image based on custom image or adapter type
    if custom_image and isinstance(custom_image, str):
        image = custom_image
    else:
        IMAGE_BASE = os.getenv("CHARM_IMAGE_BASE", "ucmind/runner-base:latest")
        ADAPTER_IMAGES = {
            "langchain": os.getenv("CHARM_IMAGE_LANGCHAIN", "ucmind/runner-langchain:latest"),
            "crewai": os.getenv("CHARM_IMAGE_CREWAI", "ucmind/runner-crewai:latest"),
            "openclaw": os.getenv("CHARM_IMAGE_OPENCLAW", "ucmind/runner-openclaw:latest"),
        }
        image = ADAPTER_IMAGES.get(adapter_type, IMAGE_BASE)

    # Build env vars with mock tokens if requested
    final_env_vars = env_vars.copy()
    if mock_oauth:
        # Inject mock OAuth tokens for known providers
        mock_tokens = {
            "GOOGLE_OAUTH_TOKEN": "mock_google_token_12345",
            "GITHUB_OAUTH_TOKEN": "mock_github_token_12345",
            "NOTION_OAUTH_TOKEN": "mock_notion_token_12345",
        }
        final_env_vars.update(mock_tokens)
        console.print("[dim]Using mock OAuth tokens (--mock-oauth)[/dim]")

    # Skip actual skill connections if mock_skills is set
    if mock_skills and skills:
        console.print(f"[dim]Mocking {len(skills)} skills (--mock-skills)[/dim]")

    # Metrics tracking
    start_time = time.time()
    token_count = 0
    llm_calls = 0
    tools_invoked = 0

    console.print(
        Panel(
            f"Mounting: [cyan]{abs_path}[/cyan]\n"
            f"Environment: [cyan]{len(final_env_vars)} variables[/cyan]\n"
            f"Adapter: [cyan]{adapter_type}[/cyan]\n"
            f"Mode: [cyan]{runtime_mode}[/cyan]\n"
            f"Lifecycle: [cyan]{lifecycle}[/cyan]"
            + (f"\nImage: [cyan]{image}[/cyan]" if image else ""),
            title="[bold blue]🚀 Starting Docker Simulation[/bold blue]",
            border_style="blue",
        )
    )

    try:
        async for sse_line in executor.run(
            agent_id="local_sim",
            input_payload=payload,
            env_vars=final_env_vars,
            file_urls={},
            history=[],
            local_source_path=abs_path,
            image=image,
            adapter_type=adapter_type,
            skills=skills if not mock_skills else [],  # Empty if mocking
        ):
            # Track metrics from SSE events
            if sse_line.startswith("data: "):
                try:
                    data = json.loads(sse_line.replace("data: ", ""))
                    evt_type = data.get("type")
                    if evt_type == "delta":
                        token_count += 1
                    elif evt_type == "thinking":
                        # LLM call detected
                        llm_calls += 1
                    elif evt_type in ("tool", "artifact"):
                        tools_invoked += 1
                except Exception:
                    pass

            parse_and_print_sse(sse_line)

        # Show execution metrics
        elapsed_time = time.time() - start_time
        print_metrics(elapsed_time, token_count, llm_calls, tools_invoked)

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


def print_metrics(elapsed_time: float, token_count: int, llm_calls: int, tools_invoked: int):
    """Print execution metrics in a table."""
    table = Table(title="Execution Metrics", show_header=True)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Execution Time", f"{elapsed_time:.2f}s")
    table.add_row("Tokens (estimated)", str(token_count))
    table.add_row("LLM Calls", str(llm_calls))
    table.add_row("Tools Invoked", str(tools_invoked))

    console.print(table)


def load_test_cases(file_path: str) -> List[Dict[str, Any]]:
    """Load test cases from JSON file."""
    try:
        with open(file_path, "r") as f:
            data = json.load(f)

        if not isinstance(data, list):
            raise ValueError("Test file must contain a JSON array")

        # Validate each test case
        for i, case in enumerate(data):
            if not isinstance(case, dict):
                raise ValueError(f"Test case {i} must be an object")
            if "input" not in case:
                raise ValueError(f"Test case {i} missing 'input' field")

        return data
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in test file: {e}") from e


@app.command("run")
def run_command(
    path: str = typer.Argument(".", help="Path to the Charm project root"),
    input_text: Optional[str] = typer.Option(None, "--input", "-i", help="Simple text input"),
    json_input: Optional[str] = typer.Option(None, "--json", help="Raw JSON input payload"),
    input_file: Optional[str] = typer.Option(
        None, "--input-file", "-f", help="Path to test cases JSON file"
    ),
    docker: bool = typer.Option(
        False, "--docker", help="Run inside a local Docker container (Simulate Cloud)"
    ),
    mock_oauth: bool = typer.Option(
        False, "--mock-oauth", help="Use mock OAuth tokens for testing"
    ),
    mock_skills: bool = typer.Option(
        False, "--mock-skills", help="Use mock skills (skip actual MCP connections)"
    ),
    debug: bool = typer.Option(False, "--debug", help="Enable debug mode"),
):
    if debug:
        state.DEBUG_MODE = True
    """
    Run a Charm Agent locally.
    Supports both interactive mode, headless (JSON/Text) mode, and Docker Simulation.

    Test cases can be provided via --input-file with JSON format:
    [
      {"name": "Test 1", "input": {"query": "hello"}},
      {"name": "Test 2", "input": {"query": "bye"}}
    ]
    """
    # 1. Environment Loading
    env_path = os.path.join(path, ".env")
    abs_env_path = os.path.abspath(env_path)

    # We capture env vars to pass to Docker if needed
    loaded_env_vars: Dict[str, str] = {}

    if os.path.exists(env_path):
        console.print(f"[dim]Loading .env from: {abs_env_path}[/dim]")
        load_dotenv(env_path, override=True)
        # Read file robustly using dotenv_values
        try:
            raw_env = dotenv_values(env_path)
            loaded_env_vars = {k: v for k, v in raw_env.items() if v is not None}
        except Exception:
            pass

    # 2. Handle test cases from file
    if input_file:
        test_cases = load_test_cases(input_file)
        console.print(f"[bold]Running {len(test_cases)} test cases from {input_file}[/bold]\n")

        for i, case in enumerate(test_cases):
            case_name = case.get("name", f"Test {i+1}")
            case_input = case.get("input", {})

            console.print(f"[bold cyan]--- {case_name} ---[/bold cyan]")
            console.print(f"[dim]Input: {case_input}[/dim]\n")

            # Run the test
            if docker:
                asyncio.run(run_docker_simulation(path, case_input, loaded_env_vars, mock_oauth, mock_skills))
            else:
                run_local(path, case_input)

            console.print()

        console.print(f"[bold green]✓ Completed {len(test_cases)} test cases[/bold green]")
        return

    # 3. Single input preparation
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
        asyncio.run(run_docker_simulation(path, payload, loaded_env_vars, mock_oauth, mock_skills))
        return

    # MODE 2: LOCAL PYTHON EXECUTION
    run_local(path, payload, json_input)


def run_local(path: str, payload: Dict[str, Any], json_input: Optional[str] = None):
    """Run agent locally without Docker."""
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
            start_time = time.time()
            result = wrapper.invoke(payload)
            elapsed_time = time.time() - start_time
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
            # Show execution time for local mode
            console.print(f"[dim]Execution time: {elapsed_time:.2f}s[/dim]")
        else:
            error_msg = result.get("message", "Unknown error")
            console.print(
                Panel(f"[bold]Error:[/bold] {error_msg}", title="Agent Failed", border_style="red")
            )
    else:
        console.print(json.dumps(result))
