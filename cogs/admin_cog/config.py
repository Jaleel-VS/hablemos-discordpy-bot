"""Admin cog configuration."""
from config import get_int_env

VC_ENRICH_CHANNEL_ID: int = get_int_env("VC_ENRICH_CHANNEL_ID", 742449924519755878)
REMINDER_CHANNEL_ID: int = get_int_env("REMINDER_CHANNEL_ID", 296491080881537024)
REMINDER_INTERVAL_MINUTES: int = get_int_env("REMINDER_INTERVAL_MINUTES", 15)
