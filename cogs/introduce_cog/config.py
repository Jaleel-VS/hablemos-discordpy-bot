from dataclasses import dataclass
from typing import Final

import discord


@dataclass(frozen=True)
class ChannelIDs:
    COMMAND_CHANNEL: int = 1437832952028467251
    INTRODUCTIONS_CHANNEL: int = 1464254572204916969


CHANNELS = ChannelIDs()

# Embed colors
INTRO_COLOR = discord.Color.greyple()  # Gray/neutral for intro-only
EXCHANGE_COLOR = discord.Color.teal()  # Green/teal for seeking exchange partner

# Language options for select menus
LANGUAGES: Final[list[tuple[str, str]]] = [
    ("English", "english"),
    ("Spanish", "spanish"),
    ("Portuguese", "portuguese"),
    ("French", "french"),
    ("German", "german"),
    ("Italian", "italian"),
    ("Japanese", "japanese"),
    ("Korean", "korean"),
    ("Chinese (Mandarin)", "chinese_mandarin"),
    ("Chinese (Cantonese)", "chinese_cantonese"),
    ("Russian", "russian"),
    ("Arabic", "arabic"),
    ("Dutch", "dutch"),
    ("Polish", "polish"),
    ("Turkish", "turkish"),
    ("Vietnamese", "vietnamese"),
    ("Thai", "thai"),
    ("Hindi", "hindi"),
    ("Swedish", "swedish"),
    ("Norwegian", "norwegian"),
    ("Danish", "danish"),
    ("Finnish", "finnish"),
    ("Greek", "greek"),
    ("Hebrew", "hebrew"),
    ("Indonesian", "indonesian"),
]

# Proficiency levels
PROFICIENCY_LEVELS: Final[list[tuple[str, str]]] = [
    ("Native", "native"),
    ("Advanced (C1-C2)", "advanced"),
    ("Intermediate (B1-B2)", "intermediate"),
    ("Beginner (A1-A2)", "beginner"),
]

# Common timezones grouped by region
TIMEZONES: Final[list[tuple[str, str]]] = [
    ("UTC-12:00 (Baker Island)", "UTC-12"),
    ("UTC-11:00 (Samoa)", "UTC-11"),
    ("UTC-10:00 (Hawaii)", "UTC-10"),
    ("UTC-09:00 (Alaska)", "UTC-9"),
    ("UTC-08:00 (Pacific US)", "UTC-8"),
    ("UTC-07:00 (Mountain US)", "UTC-7"),
    ("UTC-06:00 (Central US/Mexico)", "UTC-6"),
    ("UTC-05:00 (Eastern US/Colombia)", "UTC-5"),
    ("UTC-04:00 (Atlantic/Venezuela)", "UTC-4"),
    ("UTC-03:00 (Argentina/Brazil)", "UTC-3"),
    ("UTC-02:00 (Mid-Atlantic)", "UTC-2"),
    ("UTC-01:00 (Azores)", "UTC-1"),
    ("UTC+00:00 (UK/Portugal)", "UTC+0"),
    ("UTC+01:00 (Central Europe)", "UTC+1"),
    ("UTC+02:00 (Eastern Europe)", "UTC+2"),
    ("UTC+03:00 (Moscow/Turkey)", "UTC+3"),
    ("UTC+04:00 (Dubai/Baku)", "UTC+4"),
    ("UTC+05:00 (Pakistan)", "UTC+5"),
    ("UTC+05:30 (India)", "UTC+5:30"),
    ("UTC+06:00 (Bangladesh)", "UTC+6"),
    ("UTC+07:00 (Thailand/Vietnam)", "UTC+7"),
    ("UTC+08:00 (China/Singapore)", "UTC+8"),
    ("UTC+09:00 (Japan/Korea)", "UTC+9"),
    ("UTC+10:00 (Sydney)", "UTC+10"),
    ("UTC+12:00 (New Zealand)", "UTC+12"),
]

# Countries for partner preference
COUNTRIES: Final[list[tuple[str, str]]] = [
    ("No Preference", "no_preference"),
    ("Spain", "spain"),
    ("England", "england"),
    ("Mexico", "mexico"),
]
