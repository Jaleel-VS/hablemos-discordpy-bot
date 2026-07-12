"""Centralized env config for the Activity backend.

Mirrors the root project's ``config.py`` helper style (typed getters with
defaults) so ``None`` is handled once, at the boundary, and callers receive
concrete values.
"""
import os
from dataclasses import dataclass


def get_str_env(name: str, default: str = "") -> str:
    """Return an env var as a string, or ``default`` when unset/blank."""
    value = os.getenv(name)
    return value if value else default


def get_required_env(name: str) -> str:
    """Return a required env var, raising a clear error when missing."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def get_int_env(name: str, default: int) -> int:
    """Return an env var as an int, falling back to ``default`` on unset/bad."""
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    """Resolved Activity backend configuration."""

    discord_client_id: str
    discord_client_secret: str
    port: int
    environment: str
    # Directory holding the built SPA (``frontend/dist``). Resolved to an
    # absolute path so static serving works regardless of CWD.
    static_dir: str
    # Shared PostgreSQL connection string (same DB as the bot). Empty when
    # unset — the app still serves the handshake, but game persistence is
    # disabled and stats read as zeros.
    database_url: str


def load_settings() -> Settings:
    """Load and validate settings from the environment.

    ``DISCORD_CLIENT_SECRET`` is required in every real deployment (the token
    exchange cannot happen without it); we fail fast rather than let a
    ``None`` reach the OAuth call.
    """
    default_static = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "static"),
    )
    return Settings(
        discord_client_id=get_required_env("DISCORD_CLIENT_ID"),
        discord_client_secret=get_required_env("DISCORD_CLIENT_SECRET"),
        port=get_int_env("PORT", 8080),
        environment=get_str_env("ENVIRONMENT", "production"),
        static_dir=get_str_env("ACTIVITY_STATIC_DIR", default_static),
        database_url=get_str_env("DATABASE_URL", ""),
    )
