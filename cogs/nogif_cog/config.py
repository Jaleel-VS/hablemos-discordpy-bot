"""No-GIF cog configuration."""
from config import get_int_env, get_str_env

# Name of the role the bot creates/reuses to block embed links.
NOGIF_ROLE_NAME: str = get_str_env("NOGIF_ROLE_NAME", "Sin GIFs")

# bot_settings key prefix for storing the role ID per guild.
SETTING_KEY_PREFIX = "nogif.role_id"

# Maximum restriction duration in seconds (default: 30 days).
NOGIF_MAX_SECONDS: int = get_int_env("NOGIF_MAX_SECONDS", 30 * 24 * 3600)

__all__ = [
    "NOGIF_MAX_SECONDS",
    "NOGIF_ROLE_NAME",
    "SETTING_KEY_PREFIX",
]
