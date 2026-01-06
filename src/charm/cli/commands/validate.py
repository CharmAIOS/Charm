import ast
import importlib.util
import inspect
import os
import sys
from pathlib import Path

import typer
import yaml  # type: ignore
from rich.console import Console
from rich.panel import Panel

from ...contracts.uac import CharmConfig

console = Console()


def _check_absolute_paths(project_path: Path) -> list:
    """
    Scans python files for hardcoded absolute paths using AST.
    Returns a list of warnings.
    """
    warnings = []
    ignored_dirs = {".venv", "venv", ".git", "__pycache__", "node_modules", "dist", "build"}

    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in ignored_dirs]

        for file in files:
            if file.endswith(".py"):
                file_path = Path(root) / file
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        tree = ast.parse(f.read())

                    for node in ast.walk(tree):
                        if isinstance(node, ast.Constant) and isinstance(node.value, str):
                            val = node.value
                            is_unix_abs = val.startswith("/") and len(val) > 1 and "/" in val[1:]
                            is_win_abs = len(val) > 2 and val[1] == ":" and val[2] in ["\\", "/"]

                            if (is_unix_abs or is_win_abs) and not val.startswith(
                                ("http", "https", "application/", "text/")
                            ):
                                rel_path = file_path.relative_to(project_path)
                                warnings.append(
                                    f"{rel_path}:{node.lineno} -> Suspicious absolute path: '{val}'"
                                )
                except Exception:
                    pass
    return warnings


def _check_entry_point_signature(project_path: Path, entry_point_str: str) -> list:
    """
    Validates that the entry point function accepts the correct arguments.
    """
    errors = []
    if ":" not in entry_point_str:
        return ["Entry point format invalid. Expected 'module:function'"]

    module_name, func_name = entry_point_str.split(":")

    original_sys_path = sys.path[:]
    sys.path.insert(0, str(project_path))

    try:
        module_file = project_path / Path(module_name.replace(".", "/") + ".py")
        if not module_file.exists():
            module_file = project_path / Path(module_name.replace(".", "/") + "/__init__.py")

        if not module_file.exists():
            return [f"Could not find module file for '{module_name}'"]

        spec = importlib.util.spec_from_file_location(module_name, module_file)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            if not hasattr(module, func_name):
                return [f"Function/Object '{func_name}' not found in module '{module_name}'"]

            obj = getattr(module, func_name)

            if callable(obj):
                try:
                    sig = inspect.signature(obj)
                    if len(sig.parameters) == 0:
                        return []
                    valid_params = {"inputs", "callbacks"}

                    for name, param in sig.parameters.items():
                        if (
                            name not in valid_params
                            and param.default == inspect.Parameter.empty
                            and param.kind != inspect.Parameter.VAR_KEYWORD
                        ):
                            errors.append(
                                f"Entry point '{func_name}' has an unsupported required argument: '{name}'.\n"
                                f"    Only 'inputs' and 'callbacks' are provided by Charm Runtime."
                            )
                except ValueError:
                    pass

    except Exception as e:
        errors.append(f"Could not statically analyze entry point (Import Error): {e}")
    finally:
        sys.path = original_sys_path

    return errors


def validate_command(path: str = typer.Argument(".", help="Path to the Charm project root")):
    """
    Validate the charm.yaml configuration and check code integrity.
    """
    project_path = Path(path).resolve()
    yaml_file = project_path / "charm.yaml"

    if not yaml_file.exists():
        console.print(f"[bold red] Error:[/bold red] charm.yaml not found in {project_path}")
        console.print("Are you in the right directory?")
        raise typer.Exit(code=2)

    # YAML Schema Validation
    try:
        with open(yaml_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        config = CharmConfig(**data)
    except Exception as e:
        console.print(f"[bold red]✖ Configuration Error:[/bold red] {e}")
        raise typer.Exit(code=1) from e

    console.print(
        Panel(
            f"[bold]Agent:[/bold] {config.persona.name} (v{config.persona.version})\n"
            f"[bold]Adapter:[/bold] {config.runtime.adapter.type}",
            title="[bold green]✔ Schema Valid[/bold green]",
            border_style="green",
        )
    )

    # Code Static Analysis (Linting)
    console.print("\n[bold]Running Code Analysis...[/bold]")
    issues_found = False

    # Entry Point Signature
    if config.runtime.adapter.type == "custom":
        ep_errors = _check_entry_point_signature(project_path, config.runtime.adapter.entry_point)
        if ep_errors:
            issues_found = True
            console.print("[bold red]✖ Entry Point Contract Violation:[/bold red]")
            for err in ep_errors:
                console.print(f"  - {err}")
        else:
            console.print("[green]✔ Entry Point Signature looks correct.[/green]")

    # Absolute Paths
    path_warnings = _check_absolute_paths(project_path)
    if path_warnings:
        console.print(
            "\n[bold yellow]⚠ Portability Warnings (Absolute Paths Detected):[/bold yellow]"
        )
        console.print("  [dim]Absolute paths will break when running in the cloud.[/dim]")
        for w in path_warnings[:5]:
            console.print(f"  - {w}")
        if len(path_warnings) > 5:
            console.print(f"  - ... and {len(path_warnings) - 5} more.")
    else:
        console.print("[green]✔ No hardcoded absolute paths detected.[/green]")

    if issues_found:
        console.print("\n[bold red]Validation Failed due to code issues.[/bold red]")
        raise typer.Exit(code=1)

    console.print("\n[bold green]✨ Project is ready to push![/bold green]")
