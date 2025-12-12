import typer
import importlib.metadata
from typing import Optional

from .commands import auth, run, validate, push

app = typer.Typer(
    name="charm",
    help="Charm CLI - The Universal Agent Runtime Manager",
    add_completion=False,
    no_args_is_help=True
)

app.command(name="run")(run.run_command)
app.command(name="auth")(auth.auth_command)
app.command(name="validate")(validate.validate_command)
app.command(name="push")(push.push_command)

def version_callback(value: bool):
    if value:
        try:
            version = importlib.metadata.version("charmos")
        except importlib.metadata.PackageNotFoundError:
            version = "dev"
        typer.echo(f"Charm CLI Version: {version}")
        raise typer.Exit()

@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None, 
        "--version", 
        "-v", 
        help="Show the CLI version and exit.", 
        callback=version_callback, 
        is_eager=True
    )
):
    """
    The main entry point for Charm CLI.
    """
    pass

if __name__ == "__main__":
    app()