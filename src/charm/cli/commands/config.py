import typer
import tomlkit
from rich.console import Console
from rich.table import Table
from ...cli.config import load_config, CONFIG_FILE

app = typer.Typer(help="Manage local configuration.")
console = Console()

@app.command("set")
def set_config(key: str, value: str):
    """Set a config value. Usage: charm config set core.api_base http://localhost:3000/api"""
    if "." not in key:
        console.print("[bold red]Error:[/bold red] Key must be 'section.key'")
        raise typer.Exit(code=1)
    section, subkey = key.split(".", 1)
    config = load_config()
    if section not in config: config.add(section, tomlkit.table())
    config[section][subkey] = value
    
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        f.write(tomlkit.dumps(config))
    console.print(f"[green]✔ set {key} = {value}[/green]")

@app.command("list")
def list_config():
    """List current config."""
    config = load_config()
    console.print(f"[bold]Config:[/bold] {CONFIG_FILE}")
    console.print(config)