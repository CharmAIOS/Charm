import ast
import importlib.util
import inspect
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import typer
import yaml  # type: ignore
from rich.console import Console
from rich.panel import Panel

from ... import __version__ as CHARM_SDK_VERSION
from ...contracts.uac import CharmConfig

console = Console()

# Valid adapter types (from UAC contract)
def get_valid_adapter_types() -> List[str]:
    from importlib.metadata import entry_points
    try:
        eps = entry_points(group="charm.adapters")
        return [ep.name for ep in eps]
    except Exception:
        return ["python", "crewai", "langchain", "langgraph", "openclaw", "node", "custom"]

VALID_ADAPTER_TYPES = get_valid_adapter_types()

# Latest supported version
LATEST_VERSION = "0.4"


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


def _check_entry_point_signature(project_path: Path, entry_point_str: str) -> List[str]:
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


def _validate_auth_providers(config: CharmConfig) -> List[str]:
    """Validate auth providers configuration."""
    errors: List[str] = []

    if not config.auth:
        return errors

    valid_provider_names = ["google", "github", "notion", "slack", "intercom", "custom"]

    for provider in config.auth.providers:
        # Check provider name
        if provider.name not in valid_provider_names and not provider.name.startswith("custom:"):
            errors.append(f"Auth provider '{provider.name}' may not be recognized. Consider: {', '.join(valid_provider_names)}")

    return errors


def _validate_runtime_skills(config: CharmConfig) -> List[str]:
    """Validate runtime skills configuration."""
    warnings: List[str] = []

    if not config.runtime or not config.runtime.skills:
        return warnings

    valid_sources = ["git:", "https://", "npm:", "pip:", "smithery:", "local:"]

    for skill in config.runtime.skills:
        source = skill.source
        if not any(source.startswith(prefix) for prefix in valid_sources):
            warnings.append(f"Skill '{skill.name}' has unusual source: '{source}'. Valid prefixes: {', '.join(valid_sources)}")

    return warnings


def _validate_policies(config: CharmConfig) -> List[str]:
    """Validate policies configuration."""
    warnings: List[str] = []

    if not config.policies:
        return warnings

    # Check execution timeout
    if hasattr(config.policies, 'execution_timeout_seconds'):
        timeout = config.policies.execution_timeout_seconds
        if timeout and timeout > 3600:  # > 1 hour
            warnings.append(f"Execution timeout of {timeout}s is very long. Consider using daemon lifecycle for long-running agents.")
        elif timeout and timeout < 10:
            warnings.append(f"Execution timeout of {timeout}s is very short. Agent may not complete tasks.")

    # Check max steps
    if hasattr(config.policies, 'max_steps'):
        max_steps = config.policies.max_steps
        if max_steps and max_steps > 200:
            warnings.append(f"Max steps of {max_steps} is high. This may result in long execution times and high costs.")

    return warnings


def _validate_pricing(config: CharmConfig) -> List[str]:
    """Validate pricing configuration."""
    warnings: List[str] = []

    if not config.pricing:
        return warnings

    pricing = config.pricing

    # Check pricing model
    valid_models = ["free", "usage_based", "one_time", "subscription"]
    if pricing.model not in valid_models:
        warnings.append(f"Pricing model '{pricing.model}' is not standard. Valid models: {', '.join(valid_models)}")

    return warnings


def _validate_interface_state(config: CharmConfig) -> List[str]:
    """Validate interface.state definition (spec item 3.3).

    interface.state is parsed by Pydantic into an InterfaceState model:
        format: "json" | "binary" | "pydantic_model"
        schema:  <JSON Schema dict describing the state object>

    We validate the inner schema dict for correctness.
    """
    warnings: List[str] = []

    if not config.interface:
        return warnings

    state = config.interface.state
    if state is None:
        return warnings  # Optional — absence is fine

    # state is an InterfaceState pydantic model; validate its inner schema dict
    schema = state.schema_  # aliased from "schema:" in YAML

    if not schema:
        warnings.append(
            "interface.state.schema is empty — "
            "define the structure of your state object (e.g. type: object, properties: ...)"
        )
        return warnings

    # Schema should describe an object (state is always a key-value mapping at runtime)
    if schema.get("type") != "object":
        warnings.append(
            "interface.state.schema should have 'type: object' — "
            "state is always a key-value mapping at runtime"
        )

    # Must declare properties so the platform knows what fields to expose
    if "properties" not in schema:
        warnings.append(
            "interface.state.schema is missing 'properties' — "
            "declare named state fields so the platform can surface them"
        )
    else:
        props = schema["properties"]
        if not isinstance(props, dict):
            warnings.append("interface.state.schema.properties must be a mapping of field names to schemas")
        else:
            for field_name, field_schema in props.items():
                if not isinstance(field_schema, dict):
                    warnings.append(
                        f"interface.state.schema.properties.{field_name} must be a JSON Schema object"
                    )
                elif "type" not in field_schema:
                    warnings.append(
                        f"interface.state.schema.properties.{field_name} is missing a 'type' field"
                    )

    # additionalProperties should be explicit to avoid silent key sprawl
    if "additionalProperties" not in schema:
        warnings.append(
            "interface.state.schema has no 'additionalProperties' — "
            "consider setting it to false to prevent undeclared keys"
        )

    return warnings


def _validate_adapter_type(config: CharmConfig) -> List[str]:
    """Validate adapter type and required fields."""
    errors = []

    adapter_type = config.runtime.adapter.type

    # Check if adapter type is valid
    if adapter_type not in VALID_ADAPTER_TYPES:
        errors.append(f"Adapter type '{adapter_type}' is not recognized. Valid types: {', '.join(VALID_ADAPTER_TYPES)}")
        return errors

    # Type-specific validation
    if adapter_type == "node":
        if not config.runtime.adapter.entry_point or not config.runtime.adapter.entry_point.strip():
            errors.append("Node adapter requires a non-empty 'entry_point' (e.g., 'npm start')")

    elif adapter_type == "openclaw":
        # OpenClaw should have config with system_prompt
        if not config.runtime.config:
            errors.append("OpenClaw adapter requires 'runtime.config' with 'system_prompt'")
        elif not config.runtime.config.system_prompt:
            errors.append("OpenClaw adapter requires 'system_prompt' in runtime.config")

    elif adapter_type not in ("openclaw", "node"):
        if not config.runtime.adapter.entry_point or not config.runtime.adapter.entry_point.strip():
            errors.append(f"{adapter_type} adapter requires a non-empty 'entry_point' (e.g., 'src.main:agent')")

    return errors


def _check_version_compatibility(config: CharmConfig) -> Dict[str, Any]:
    """Check if charm.yaml version is compatible with SDK."""
    yaml_version = config.version

    # Extract major.minor from version
    try:
        version_parts = yaml_version.split(".")
        if len(version_parts) >= 2:
            yaml_major_minor = f"{version_parts[0]}.{version_parts[1]}"
        else:
            yaml_major_minor = yaml_version
    except Exception:
        yaml_major_minor = yaml_version

    sdk_parts = CHARM_SDK_VERSION.split(".")
    if len(sdk_parts) >= 2:
        sdk_major_minor = f"{sdk_parts[0]}.{sdk_parts[1]}"
    else:
        sdk_major_minor = CHARM_SDK_VERSION

    is_compatible = yaml_major_minor == sdk_major_minor

    return {
        "yaml_version": yaml_version,
        "sdk_version": CHARM_SDK_VERSION,
        "is_compatible": is_compatible,
        "warning": not is_compatible
    }


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

    # Version Compatibility Check
    version_info = _check_version_compatibility(config)
    if version_info["warning"]:
        console.print(f"[yellow]⚠ Warning: Using charm.yaml version '{version_info['yaml_version']}'[/yellow]")
        console.print(f"[yellow]   SDK version is '{version_info['sdk_version']}'. Consider upgrading to latest '0.4.x'.[/yellow]")
    else:
        console.print(f"[dim]Version: charm.yaml {version_info['yaml_version']} (compatible with SDK {version_info['sdk_version']})[/dim]")

    # New UAC Field Validations
    console.print("\n[bold]Validating UAC Fields...[/bold]")

    # Auth Providers
    auth_errors = _validate_auth_providers(config)
    if auth_errors:
        console.print("[yellow]⚠ Auth Providers:[/yellow]")
        for err in auth_errors:
            console.print(f"  - {err}")
    else:
        console.print("[green]✔ Auth providers configured correctly.[/green]")

    # Runtime Skills
    skill_warnings = _validate_runtime_skills(config)
    if skill_warnings:
        console.print("[yellow]⚠ Runtime Skills:[/yellow]")
        for w in skill_warnings:
            console.print(f"  - {w}")
    else:
        console.print("[green]✔ Runtime skills configured correctly.[/green]")

    # Policies
    policy_warnings = _validate_policies(config)
    if policy_warnings:
        console.print("[yellow]⚠ Policies:[/yellow]")
        for w in policy_warnings:
            console.print(f"  - {w}")
    else:
        console.print("[green]✔ Policies configured correctly.[/green]")

    # Pricing
    pricing_warnings = _validate_pricing(config)
    if pricing_warnings:
        console.print("[yellow]⚠ Pricing:[/yellow]")
        for w in pricing_warnings:
            console.print(f"  - {w}")
    else:
        console.print("[green]✔ Pricing configured correctly.[/green]")

    # Interface State Schema
    state_warnings = _validate_interface_state(config)
    if state_warnings:
        console.print("[yellow]⚠ Interface State:[/yellow]")
        for w in state_warnings:
            console.print(f"  - {w}")
    elif getattr(getattr(config, "interface", None), "state", None) is not None:
        console.print("[green]✔ Interface state schema is valid.[/green]")

    # Adapter Type Validation (improved)
    adapter_errors = _validate_adapter_type(config)
    if adapter_errors:
        console.print("[bold red]✖ Adapter Configuration Errors:[/bold red]")
        for err in adapter_errors:
            console.print(f"  - {err}")
        raise typer.Exit(code=1)

    # Code Static Analysis
    console.print("\n[bold]Running Code Analysis...[/bold]")
    issues_found = False

    # Conditional Validation based on Adapter Type
    if config.runtime.adapter.type == "node":
        # Node.js specific checks
        package_json = project_path / "package.json"
        if not package_json.exists():
            issues_found = True
            console.print("[bold red]✖ Missing package.json for Node.js agent.[/bold red]")
        else:
            console.print("[green]✔ package.json found.[/green]")
        entry_point = config.runtime.adapter.entry_point or ""
        if not entry_point.strip():
            issues_found = True
            console.print("[bold red]✖ Entry point command cannot be empty.[/bold red]")

    elif config.runtime.adapter.type not in ("openclaw", "node"):
        # Python checks
        entry_point = config.runtime.adapter.entry_point or ""
        ep_errors = _check_entry_point_signature(project_path, entry_point)
        if ep_errors:
            issues_found = True
            console.print("[bold red]✖ Entry Point Contract Violation:[/bold red]")
            for err in ep_errors:
                console.print(f"  - {err}")
        else:
            console.print("[green]✔ Entry Point Signature looks correct.[/green]")

        # Absolute Paths (Python code)
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

    elif config.runtime.adapter.type == "openclaw":
        console.print("[green]✔ OpenClaw adapter configured correctly.[/green]")

    if issues_found:
        console.print("\n[bold red]Validation Failed due to code issues.[/bold red]")
        raise typer.Exit(code=1)

    console.print("\n[bold green]✨ Project is ready to push![/bold green]")
