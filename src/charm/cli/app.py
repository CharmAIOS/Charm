import typer
import importlib.metadata
from typing import Optional

# 引用模組
from .commands import auth, run, validate, push

app = typer.Typer(
    name="charm",
    help="Charm CLI - The Universal Agent Runtime Manager",
    add_completion=False,
    no_args_is_help=True
)

# ---------------------------------------------------------
# 👇 修改這裡：原本是 app.command，現在改成 app.add_typer
# 這樣你的指令就會變成 'charm auth login', 'charm auth whoami'
# ---------------------------------------------------------
app.add_typer(auth.app, name="auth", help="Login, logout, and manage credentials")

# 其他指令保持不變
app.command(name="run")(run.run_command)
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