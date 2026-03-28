"""
Centralized environment configuration.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


def get_required_env(name: str) -> str:
    """Return required environment variable or raise ValueError."""
    value = os.getenv(name)
    if not value:
        raise ValueError(f"{name} environment variable is required")
    return value


def get_int_env(name: str, default: int | str) -> int:
    """Return int environment variable with default fallback."""
    value = os.getenv(name)
    if value is None or value == "":
        return int(default)
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def get_str_env(name: str, default: str) -> str:
    """Return string environment variable with default fallback."""
    value = os.getenv(name)
    return value if value not in (None, "") else default


def get_list_env(name: str, default: list[str]) -> list[str]:
    """Return comma-delimited environment variable as list of strings."""
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return [part.strip() for part in value.split(',') if part.strip()]


@dataclass(frozen=True)
class Settings:
    """Application settings loaded from environment variables."""

    bot_token: str
    database_url: str
    prefix: str
    bot_playground_guild_id: int
    error_channel_id: int
    online_channel_id: int
    league_guild_id: int
    owner_id: int
    gemini_api_key: str
    environment: str
    website_api_url: str
    convo_spa_channels: list[int]
    intro_channel_id: int
    general_channel_id: int
    intro_warn_channel_id: int
    intro_alert_channel_id: int


def load_settings() -> Settings:
    """Load settings from environment variables."""
    convo_spa_defaults = [
        "809349064029241344",
        "243858509123289089",
        "388539967053496322",
        "477630693292113932",
    ]
    return Settings(
        bot_token=get_required_env("BOT_TOKEN"),
        database_url=get_required_env("DATABASE_URL"),
        prefix=get_str_env("PREFIX", "$"),
        bot_playground_guild_id=get_int_env("BOT_PLAYGROUND_GUILD_ID", "731403448502845501"),
        error_channel_id=get_int_env("ERROR_CHANNEL_ID", "811669166883995690"),
        online_channel_id=get_int_env("ONLINE_CHANNEL_ID", "808679873837137940"),
        league_guild_id=get_int_env("LEAGUE_GUILD_ID", "243838819743432704"),
        owner_id=get_int_env("BOT_OWNER_ID", "216848576549093376"),
        gemini_api_key=get_required_env("GEMINI_API_KEY"),
        environment=get_str_env("ENVIRONMENT", "development"),
        website_api_url=get_str_env(
            "WEBSITE_API_URL",
            "https://spa-eng-discord-website-backend-production.up.railway.app/api",
        ),
        convo_spa_channels=[
            int(channel_id)
            for channel_id in get_list_env("CONVO_SPA_CHANNELS", convo_spa_defaults)
        ],
        intro_channel_id=get_int_env("INTRO_CHANNEL_ID", "399713966781235200"),
        general_channel_id=get_int_env("GENERAL_CHANNEL_ID", "296491080881537024"),
        intro_warn_channel_id=get_int_env("INTRO_WARN_CHANNEL_ID", "247135634265735168"),
        intro_alert_channel_id=get_int_env("INTRO_ALERT_CHANNEL_ID", "297877202538594304"),
    )
