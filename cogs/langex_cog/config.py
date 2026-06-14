"""Configuration for the Language Exchange cog.

Centralizes channel IDs, the offer/seek language lists, proficiency
levels, regions, and DM preference options. All IDs are overridable via
env vars (through the root ``config.py`` helpers) so they can change per
deployment without code edits.
"""
from typing import Final

import discord

from config import get_int_env

# CHANNELS

# Channel hosting the persistent panel (Post / Find buttons).
# NOTE: temporarily pointed at a test channel while the feature is in
# testing — change back to the real langex channel before going live.
PANEL_CHANNEL_ID: Final[int] = get_int_env("LANGEX_PANEL_CHANNEL_ID", 1515639236164980778)

# Channel where profile embeds are posted (the browsable feed). Also a
# test channel for now (see note above).
FEED_CHANNEL_ID: Final[int] = get_int_env("LANGEX_FEED_CHANNEL_ID", 1515641245471473704)

# Channel for audit-log embeds (post/update/delete). Reuses the introduce
# audit channel by default.
AUDIT_CHANNEL_ID: Final[int] = get_int_env("LANGEX_AUDIT_CHANNEL_ID", 1476661597970628719)

# NATIVE-LANGUAGE ROLES (for bilingual UI + embed color)

SPANISH_NATIVE_ROLE_ID: Final[int] = get_int_env("SPANISH_NATIVE_ROLE_ID", 243854128424550401)
ENGLISH_NATIVE_ROLE_ID: Final[int] = get_int_env("ENGLISH_NATIVE_ROLE_ID", 243853718758359040)
OTHER_NATIVE_ROLE_ID: Final[int] = get_int_env("OTHER_NATIVE_ROLE_ID", 247020385730691073)

# EMBED COLORS (by native-language role combo)

COLOR_ENGLISH_NATIVE: Final[discord.Color] = discord.Color.blue()
COLOR_SPANISH_NATIVE: Final[discord.Color] = discord.Color.dark_green()
COLOR_BOTH_NATIVE: Final[discord.Color] = discord.Color.orange()
COLOR_OTHER_NATIVE: Final[discord.Color] = discord.Color.purple()

# REPOST / UPDATE COOLDOWN

REPOST_GRACE_MINUTES: Final[int] = 10
REPOST_COOLDOWN_DAYS: Final[int] = 14

# LANGUAGE OPTIONS

# Language you OFFER (native / can teach).
OFFER_LANGUAGES: Final[list[tuple[str, str]]] = [
    ("English", "english"),
    ("Spanish", "spanish"),
    ("Other", "other"),
]

# Language you SEEK (the server's two learning languages).
SEEK_LANGUAGES: Final[list[tuple[str, str]]] = [
    ("English", "english"),
    ("Spanish", "spanish"),
]

# Flag emoji per language value, for compact match lines.
LANG_FLAGS: Final[dict[str, str]] = {
    "english": "🇬🇧",
    "spanish": "🇪🇸",
    "other": "🌐",
}

# Proficiency in your TARGET language (the one you're learning). Ordered
# strongest → weakest; the index is used for level-fit scoring.
PROFICIENCY_LEVELS: Final[list[tuple[str, str]]] = [
    ("C2 (Proficient)", "C2"),
    ("C1 (Advanced)", "C1"),
    ("B2 (Upper Intermediate)", "B2"),
    ("B1 (Intermediate)", "B1"),
    ("A2 (Elementary)", "A2"),
    ("A1 (Beginner)", "A1"),
]

# REGIONS (broad, inclusive). Second element of the tuple is the value
# stored in post_data; the leading hemisphere emoji is used to bucket
# regions for "nearby" scoring.
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

# Region value → hemisphere bucket (the leading globe emoji groups them).
REGION_BUCKET: Final[dict[str, str]] = {
    "north_america": "americas",
    "central_america": "americas",
    "south_america": "americas",
    "western_europe": "emea",
    "eastern_europe": "emea",
    "africa": "emea",
    "middle_east": "apac",
    "south_asia": "apac",
    "east_asia": "apac",
    "oceania": "apac",
}

# DM preference.
DM_OPTIONS: Final[list[tuple[str, str]]] = [
    ("Yes — contact me via DM", "yes"),
    ("No — tag me in the server", "no"),
]

# MATCHING WEIGHTS (see matching.py)

MATCH_RESULT_LIMIT: Final[int] = 10


def detect_ui_lang(member: discord.Member) -> str:
    """Return 'es' for Spanish-only natives, 'en' for everyone else."""
    role_ids = {r.id for r in member.roles}
    if SPANISH_NATIVE_ROLE_ID in role_ids and ENGLISH_NATIVE_ROLE_ID not in role_ids:
        return "es"
    return "en"
