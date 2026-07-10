"""Configuration for the breakdown cog."""

from config import get_int_env

# Channel where $breakdown is allowed
ALLOWED_CHANNEL_ID: int = get_int_env(
    "BREAKDOWN_CHANNEL_ID", 296491080881537024
)

# Cooldown between uses (seconds) per user
COOLDOWN_SECONDS: int = get_int_env("BREAKDOWN_COOLDOWN", 15)

# Maximum sentence length (characters)
MAX_INPUT_LENGTH: int = 500

# Minimum input length to attempt breakdown
MIN_INPUT_LENGTH: int = 5
