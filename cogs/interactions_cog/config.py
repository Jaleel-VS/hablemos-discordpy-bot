"""Configuration for the Interactions cog."""
from config import get_int_env

INTERACTIONS_RETENTION_DAYS: int = get_int_env("INTERACTIONS_RETENTION_DAYS", 90)
