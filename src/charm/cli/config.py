import os
from pathlib import Path
import tomlkit
from typing import Optional

CONFIG_DIR = Path.home() / ".charm"
CONFIG_FILE = CONFIG_DIR / "config.toml"

DEFAULT_CONFIG = {
    "core": {
        "api_base": "https://charm-registry.vercel.app"
    },
    "auth": {
        "token": "",
        "email": ""
    }
}

def _ensure_config_exists():
    if not CONFIG_DIR.exists():
        CONFIG_DIR.mkdir(parents=True)
    
    if not CONFIG_FILE.exists():
        doc = tomlkit.document()
        doc.add("core", DEFAULT_CONFIG["core"])
        doc.add("auth", DEFAULT_CONFIG["auth"])
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            f.write(tomlkit.dumps(doc))

def load_config() -> tomlkit.TOMLDocument:
    _ensure_config_exists()
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return tomlkit.parse(f.read())
    except Exception:
        return tomlkit.item(DEFAULT_CONFIG)

def save_token(token: str):
    config = load_config()
    if "auth" not in config:
        config.add("auth", tomlkit.table())
    
    config["auth"]["token"] = token
    
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        f.write(tomlkit.dumps(config))

def save_auth_data(token: str, email: str):
    config = load_config()
    if "auth" not in config:
        config.add("auth", tomlkit.table())
    
    config["auth"]["token"] = token
    config["auth"]["email"] = email
    
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        f.write(tomlkit.dumps(config))

def get_token() -> Optional[str]:
    config = load_config()
    return config.get("auth", {}).get("token")

def get_email() -> Optional[str]:
    config = load_config()
    return config.get("auth", {}).get("email")
