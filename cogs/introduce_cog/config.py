"""Configuration for the Introduce cog."""
from typing import Final

import discord

from config import get_int_env

# Channel IDs
COMMAND_CHANNEL_ID: Final[int] = get_int_env("INTRODUCE_COMMAND_CHANNEL_ID", 1437832952028467251)
INTRODUCTIONS_CHANNEL_ID: Final[int] = get_int_env("INTRODUCE_CHANNEL_ID", 1464254572204916969)
AUDIT_CHANNEL_ID: Final[int] = get_int_env("INTRODUCE_AUDIT_CHANNEL_ID", 1476661597970628719)

# Native-language role IDs
SPANISH_NATIVE_ROLE_ID: Final[int] = get_int_env("SPANISH_NATIVE_ROLE_ID", 243854128424550401)
ENGLISH_NATIVE_ROLE_ID: Final[int] = get_int_env("ENGLISH_NATIVE_ROLE_ID", 243853718758359040)
OTHER_NATIVE_ROLE_ID: Final[int] = get_int_env("OTHER_NATIVE_ROLE_ID", 247020385730691073)

# Embed colors based on native language role
COLOR_ENGLISH_NATIVE: Final[discord.Color] = discord.Color.blue()
COLOR_SPANISH_NATIVE: Final[discord.Color] = discord.Color.dark_green()
COLOR_BOTH_NATIVE: Final[discord.Color] = discord.Color.orange()
COLOR_OTHER_NATIVE: Final[discord.Color] = discord.Color.purple()
COLOR_INTRO: Final[discord.Color] = discord.Color.greyple()

# Repost cooldowns
REPOST_GRACE_MINUTES: Final[int] = 10
REPOST_COOLDOWN_DAYS: Final[int] = 14

# Language you OFFER (what you're native in / can teach)
OFFER_LANGUAGES: Final[list[tuple[str, str]]] = [
    ("English", "english"),
    ("Spanish", "spanish"),
    ("Other", "other"),
]

# Language you SEEK (what you want to learn — only the server's two languages)
SEEK_LANGUAGES: Final[list[tuple[str, str]]] = [
    ("English", "english"),
    ("Spanish", "spanish"),
]

# Proficiency in your TARGET language (the one you're learning)
PROFICIENCY_LEVELS: Final[list[tuple[str, str]]] = [
    ("C2 (Proficient)", "C2"),
    ("C1 (Advanced)", "C1"),
    ("B2 (Upper Intermediate)", "B2"),
    ("B1 (Intermediate)", "B1"),
    ("A2 (Elementary)", "A2"),
    ("A1 (Beginner)", "A1"),
]

# Regions — inclusive, broad, easy to pick
REGIONS: Final[list[tuple[str, str]]] = [
    ("🌎 North America", "north_america"),
    ("🌎 Central America & Caribbean", "central_america"),
    ("🌎 South America", "south_america"),
    ("🌍 Western Europe", "western_europe"),
    ("🌍 Eastern Europe", "eastern_europe"),
    ("🌍 Africa", "africa"),
    ("🌏 Middle East", "middle_east"),
    ("🌏 South & Southeast Asia", "south_asia"),
    ("🌏 East Asia", "east_asia"),
    ("🌏 Oceania", "oceania"),
]

# DM preference
DM_OPTIONS: Final[list[tuple[str, str]]] = [
    ("Yes — contact me via DM", "yes"),
    ("No — tag me in the server", "no"),
]


def detect_ui_lang(member: discord.Member) -> str:
    """Return 'es' for Spanish natives, 'en' for everyone else."""
    role_ids = {r.id for r in member.roles}
    if SPANISH_NATIVE_ROLE_ID in role_ids and ENGLISH_NATIVE_ROLE_ID not in role_ids:
        return "es"
    return "en"
