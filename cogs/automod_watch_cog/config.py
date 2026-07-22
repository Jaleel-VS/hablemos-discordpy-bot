"""Automod watch cog configuration."""
from config import get_int_env

# Fallback channel IDs — overridden at runtime via $automodwatch commands
# stored in bot_settings. 0 means "not configured".
DEFAULT_LOG_CHANNEL_ID: int = get_int_env("AUTOMOD_WATCH_LOG_CHANNEL_ID", 0)
DEFAULT_ALERT_CHANNEL_ID: int = get_int_env("AUTOMOD_WATCH_ALERT_CHANNEL_ID", 0)
