import typer
from rich.console import Console
from ..config import save_token

console = Console()

def auth_command(
    token: str = typer.Option(None, "--token", help="Directly provide token (optional)")
):
    """
    Authenticate with Charm Cloud using an API token.
    """
    console.print("[bold blue]Charm Auth[/bold blue]")
    console.print("Please visit [link]https://charm.ai/settings/tokens[/link] to get your API token.\n")

    if not token:
        token = typer.prompt("Paste your Charm CLI token", hide_input=True)

    if not token:
        console.print("[bold red] Error:[/bold red] No token provided.")
        raise typer.Exit(code=1)

    try:
        save_token(token)
        console.print(f"\n[bold green]✔ Success![/bold green] Token saved to [underline]~/.charm/config.toml[/underline]")
        console.print("You can now use `charm push` to publish your agents.")
    except Exception as e:
        console.print(f"[bold red] Error saving config:[/bold red] {e}")
        raise typer.Exit(code=1)