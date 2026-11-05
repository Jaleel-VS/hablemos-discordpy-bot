"""Configuration for the breakdown cog."""

from config import get_int_env, get_list_env

ALLOWED_CHANNEL_IDS: list[int] = [
    int(x) for x in get_list_env(
        "BREAKDOWN_CHANNEL_IDS",
        ["296491080881537024", "247135634265735168"],
    )
]

COOLDOWN_SECONDS: int = get_int_env("BREAKDOWN_COOLDOWN", 15)

MAX_INPUT_LENGTH: int = 500

MIN_INPUT_LENGTH: int = 5
