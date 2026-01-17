import fnmatch
import io
import json
import os
import tarfile
import uuid
from pathlib import Path

import httpx
import typer
import yaml  # type: ignore
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from ...contracts.uac import CharmConfig
from ..config import get_token, load_config
from ..git import GitError, get_repo_info

console = Console()

DEFAULT_API_BASE = "https://store.charmos.io/api"

IGNORE_SET = {
    ".env",
    ".env.local",
    "secrets.json",
    ".git",
    ".DS_Store",
    "__pycache__",
    "venv",
    ".venv",
    "env",
    "dist",
    "build",
    "node_modules",
    ".idea",
    ".vscode",
    ".ipynb_checkpoints",
    "egg-info",
    ".mypy_cache",
    ".pytest_cache",
    "*.pyc",
    "*.pyo",
    "*.pyd",
    "*.db",
    "*.sqlite3",
    "*.log",
}

MAX_BUNDLE_SIZE_MB = 50.0


def get_user_ignores(source_dir: Path) -> set:
    ignore_file = source_dir / ".charmignore"
    user_ignores = set()
    if ignore_file.exists():
        try:
            with open(ignore_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        user_ignores.add(line)
            console.print(f"[dim]Loaded .charmignore: {len(user_ignores)} rules[/dim]")
        except Exception:
            pass
    return user_ignores


def is_ignored(name: str, user_ignores: set) -> bool:
    all_patterns = IGNORE_SET.union(user_ignores)
    for pattern in all_patterns:
        if fnmatch.fnmatch(name, pattern):
            return True
    return False


def create_bundle(source_dir: Path) -> bytes:
    file_stream = io.BytesIO()
    user_ignores = get_user_ignores(source_dir)

    total_files = 0
    large_files = []

    with tarfile.open(fileobj=file_stream, mode="w:gz") as tar:
        for root, dirs, files in os.walk(source_dir):
            dirs[:] = [d for d in dirs if not is_ignored(d, user_ignores)]

            for file in files:
                if is_ignored(file, user_ignores):
                    continue

                full_path = Path(root) / file

                try:
                    size_mb = full_path.stat().st_size / (1024 * 1024)
                    if size_mb > 10.0:
                        large_files.append(f"{file} ({size_mb:.2f} MB)")
                except Exception:
                    pass

                arcname = full_path.relative_to(source_dir)
                tar.add(full_path, arcname=str(arcname))
                total_files += 1

    if large_files:
        console.print("[bold yellow]Warning: Large files detected:[/bold yellow]")
        for f in large_files:
            console.print(f"  - {f}")
        console.print("[dim]These might slow down the agent startup time.[/dim]")

    file_stream.seek(0)
    return file_stream.getvalue()


def ensure_agent_id(yaml_path: Path, current_data: dict) -> str:
    if "id" in current_data and current_data["id"]:
        return current_data["id"]

    new_id = str(uuid.uuid4())
    console.print(f"[yellow]ℹ Agent ID missing. Generated new ID: {new_id}[/yellow]")

    current_data["id"] = new_id

    try:
        original_content = yaml_path.read_text(encoding="utf-8")
        lines = original_content.splitlines()
        new_lines = []
        inserted = False

        for line in lines:
            new_lines.append(line)
            if not inserted and line.strip().startswith("version:"):
                new_lines.append(f'id: "{new_id}"  # [System] Unique Identity')
                inserted = True

        if not inserted:
            new_lines.insert(0, f'id: "{new_id}"  # [System] Unique Identity')

        if new_lines and new_lines[-1].strip() != "":
            new_lines.append("")

        yaml_path.write_text("\n".join(new_lines), encoding="utf-8")

    except Exception as e:
        console.print(f"[red]Failed to write ID back to file: {e}[/red]")

    return new_id


def push_command(
    path: str = typer.Argument(".", help="Path to the Charm project root"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview payload without sending"),
    api_base_override: str = typer.Option(None, "--api-base", help="Override API base URL"),
):
    project_path = Path(path).resolve()

    token = get_token()
    if not token:
        console.print("[bold red]Auth Error:[/bold red] Please run [bold]charm auth[/bold] first.")
        raise typer.Exit(code=1)

    yaml_file = project_path / "charm.yaml"
    if not yaml_file.exists():
        console.print(f"[bold red]Error:[/bold red] charm.yaml not found in {project_path}")
        raise typer.Exit(code=1)

    try:
        with open(yaml_file, "r") as f:
            uac_raw = yaml.safe_load(f)

        agent_id = ensure_agent_id(yaml_file, uac_raw)
        uac_raw["id"] = agent_id

        config = CharmConfig(**uac_raw)
        uac_payload = config.model_dump(mode="json", exclude_none=True)

        agent_name = config.persona.name
        agent_version = config.persona.version

    except Exception as e:
        console.print(f"[bold red]Config Error:[/bold red] {e}")
        raise typer.Exit(code=1) from e

    try:
        repo_info = get_repo_info(project_path)
    except GitError:
        repo_info = {"url": "", "branch": "main", "commit": "unknown", "is_dirty": "False"}

    if repo_info.get("is_dirty") == "True" and not dry_run:
        console.print("[bold yellow]Warning:[/bold yellow] Uncommitted changes detected.")

    metadata_payload = {
        "uac": uac_payload,
        "repo": {
            "url": repo_info["url"],
            "branch": repo_info["branch"],
            "commit": repo_info["commit"],
        },
    }

    with console.status("[bold green]Bundling source code & assets...[/bold green]"):
        bundle_bytes = create_bundle(project_path)
        bundle_size_mb = len(bundle_bytes) / (1024 * 1024)

    if dry_run:
        console.print(f"\n[bold blue]Dry Run:[/bold blue] Bundle Size: {bundle_size_mb:.2f} MB")
        console.print(Syntax(json.dumps(metadata_payload, indent=2), "json", theme="monokai"))
        raise typer.Exit(code=0)

    if bundle_size_mb > MAX_BUNDLE_SIZE_MB:
        console.print(
            f"[bold red]Error:[/bold red] Bundle size ({bundle_size_mb:.2f} MB) exceeds limit of {MAX_BUNDLE_SIZE_MB} MB."
        )
        console.print("Please remove large files or add them to .charmignore")
        raise typer.Exit(code=1)

    config_data = load_config()
    api_base = api_base_override or config_data.get("core", {}).get("api_base") or DEFAULT_API_BASE
    api_base = str(api_base).rstrip("/")

    headers = {"Authorization": f"Bearer {token}"}

    try:
        console.print(" Requesting upload permission...")
        token_resp = httpx.post(
            f"{api_base}/v1/agents/upload-token",
            json={"agent_name": agent_name, "version": agent_version},
            headers=headers,
            timeout=10.0,
        )

        if token_resp.status_code != 200:
            console.print(f"[bold red]Upload Init Failed:[/bold red] {token_resp.text}")
            raise typer.Exit(code=1)

        upload_data = token_resp.json()
        upload_url = upload_data.get("upload_url")
        storage_path = upload_data.get("storage_path")

        with console.status(
            f"[bold green]Uploading Bundle ({bundle_size_mb:.2f} MB)...[/bold green]"
        ):
            upload_resp = httpx.put(
                upload_url,
                content=bundle_bytes,
                headers={"Content-Type": "application/gzip"},
                timeout=300.0,
            )

            if upload_resp.status_code not in [200, 204]:
                console.print(
                    f"[bold red]Storage Upload Failed:[/bold red] {upload_resp.status_code}"
                )
                raise typer.Exit(code=1)

        console.print(" Registering version...")
        final_payload = {"metadata": metadata_payload, "storage_path": storage_path}

        reg_resp = httpx.post(
            f"{api_base}/v1/agents", json=final_payload, headers=headers, timeout=30.0
        )

        if reg_resp.status_code in [200, 201]:
            resp_data = reg_resp.json()
            agent_url = resp_data.get("url", "N/A")

            console.print(
                Panel(
                    f"[bold]Agent:[/bold] {agent_name}\n"
                    f"[bold]Version:[/bold] {agent_version}\n"
                    f"[bold]Size:[/bold] {bundle_size_mb:.2f} MB\n\n"
                    f"🔗 [link={agent_url}]{agent_url}[/link]",
                    title="[bold green]✔ Successfully Published[/bold green]",
                    border_style="green",
                )
            )
        else:
            console.print(f"[bold red]Registration Error ({reg_resp.status_code}):[/bold red]")
            try:
                err_msg = reg_resp.json().get("error", reg_resp.text)
                console.print(f"[red]{err_msg}[/red]")
            except Exception:
                console.print(reg_resp.text)
            raise typer.Exit(code=1)

    except Exception as e:
        console.print(f"[bold red]Connection Error:[/bold red] {e}")
        raise typer.Exit(code=1) from e
