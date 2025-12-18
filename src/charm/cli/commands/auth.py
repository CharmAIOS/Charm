import typer
import threading
import webbrowser
import json
import socket
from http.server import BaseHTTPRequestHandler, HTTPServer
from rich.console import Console
from ..config import save_auth_data, get_email, get_token, save_token

app = typer.Typer(help="Manage login and authentication")
console = Console()

STORE_URL = "http://localhost:3000"

class OAuthCallbackHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/callback':
            try:
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data.decode('utf-8'))
                
                access_token = data.get("access_token")
                email = data.get("user_email")

                if access_token:
                    save_auth_data(access_token, email)
                    
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*') 
                    self.end_headers()
                    self.wfile.write(json.dumps({"received": True}).encode())
                    
                    threading.Thread(target=self.server.shutdown).start()
                else:
                    self.send_error(400, "Missing token")
            except Exception as e:
                self.send_error(500)
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def log_message(self, format, *args):
        return

def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

@app.command()
def login():
    """
    Login via browser (Vercel style).
    """
    console.print("[bold blue]Charm CLI Login[/bold blue]")
    
    port = find_free_port()
    server = HTTPServer(('127.0.0.1', port), OAuthCallbackHandler)
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.start()
    
    login_url = f"{STORE_URL}/cli/login?port={port}"
    
    console.print(f"Opening browser: [underline]{login_url}[/underline]")
    console.print("Waiting for authentication...", style="yellow")
    
    webbrowser.open(login_url)
    server_thread.join()
    
    email = get_email()
    if email:
        console.print(f"[green]Successfully logged in as {email}![/green]")
    else:
        console.print("[red]Login failed.[/red]")

@app.command()
def logout():
    """Clear local credentials."""
    save_auth_data("", "")
    console.print("Logged out.")

@app.command()
def whoami():
    """Show current user."""
    email = get_email()
    token = get_token()
    if token:
        user = email if email else "Unknown User (Token only)"
        console.print(f"Logged in as: [bold cyan]{user}[/bold cyan]")
    else:
        console.print("Not logged in.")

@app.command()
def manual(token: str = typer.Option(..., prompt=True, hide_input=True)):
    """Manually paste a token."""
    save_token(token)
    console.print("Token saved.")
