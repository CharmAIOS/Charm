from pathlib import Path
from typing import Optional, cast

import tomlkit
from tomlkit.items import Table

# Define the global config directory (usually ~/.charm/).
CONFIG_DIR = Path.home() / ".charm"
CONFIG_FILE = CONFIG_DIR / "config.toml"

DEFAULT_CONFIG = {
    "core": {"api_base": "https://store.charmos.io/api"},
    "auth": {"token": "", "email": ""},
}


def _ensure_config_exists():
    """Creates the config file with defaults if it doesn't exist."""
    if not CONFIG_DIR.exists():
        CONFIG_DIR.mkdir(parents=True)

    if not CONFIG_FILE.exists():
        doc = tomlkit.document()
        doc.update(DEFAULT_CONFIG)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            f.write(tomlkit.dumps(doc))


def load_config() -> tomlkit.TOMLDocument:
    """Parses the TOML config file."""
    _ensure_config_exists()
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return tomlkit.parse(f.read())
    except Exception:
        doc = tomlkit.document()
        doc.update(DEFAULT_CONFIG)
        return doc


def save_token(token: str):
    """Retrieve the stored auth token."""
    config = load_config()
    if "auth" not in config:
        config.add("auth", tomlkit.table())

    auth_table = cast(Table, config["auth"])
    auth_table["token"] = token

    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        f.write(tomlkit.dumps(config))


def save_auth_data(token: str, email: str):
    """
    Persists the authentication token and email to disk.
    """
    config = load_config()
    if "auth" not in config:
        config.add("auth", tomlkit.table())

    auth_table = cast(Table, config["auth"])
    auth_table["token"] = token
    auth_table["email"] = email

    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        f.write(tomlkit.dumps(config))


def get_token() -> Optional[str]:
    config = load_config()
    return config.get("auth", {}).get("token")


def get_email() -> Optional[str]:
    config = load_config()
    return config.get("auth", {}).get("email")
