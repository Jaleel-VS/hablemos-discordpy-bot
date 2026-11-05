"""Conversation quota and generation settings."""
from config import get_int_env

DAILY_LIMIT = get_int_env("CONVERSATION_DAILY_LIMIT", 2)
BATCH_SIZE = get_int_env("CONVERSATION_BATCH_SIZE", 10)
