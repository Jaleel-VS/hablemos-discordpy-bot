"""Configuration for the General cog."""
from typing import Final

from config import get_int_env, get_str_env

BOT_CLIENT_ID: Final[int] = get_int_env("BOT_CLIENT_ID", 808377026330492941)
BOT_AUTHOR_ID: Final[int] = get_int_env("BOT_AUTHOR_ID", 216848576549093376)

INVITE_LINK: Final[str] = get_str_env(
    "BOT_INVITE_LINK",
    f"https://discord.com/api/oauth2/authorize"
    f"?client_id={BOT_CLIENT_ID}&permissions=3072&scope=bot",
)

REPO: Final[str] = "https://github.com/Jaleel-VS/hablemos-discordpy-bot"
DPY: Final[str] = "https://discordpy.readthedocs.io/en/latest/"
