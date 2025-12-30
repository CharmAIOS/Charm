from typing import cast

import tomlkit
import typer
from rich.console import Console
from tomlkit.items import Table

from ...cli.config import CONFIG_FILE, load_config

app = typer.Typer(help="Manage local configuration.")
console = Console()


@app.command("set")
def set_config(key: str, value: str):
    if "." not in key:
        console.print("[bold red]Error:[/bold red] Key must be 'section.key'")
        raise typer.Exit(code=1)
    section, subkey = key.split(".", 1)
    config = load_config()
    if section not in config:
        config.add(section, tomlkit.table())

    section_table = cast(Table, config[section])
    section_table[subkey] = value

    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        f.write(tomlkit.dumps(config))
    console.print(f"[green]✔ set {key} = {value}[/green]")


@app.command("list")
def list_config():
    config = load_config()
    console.print(f"[bold]Config:[/bold] {CONFIG_FILE}")
    console.print(config)
