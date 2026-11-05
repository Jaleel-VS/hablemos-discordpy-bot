"""Configuration for the stats cog."""

from cogs.utils.guild import (
    ENGLISH_NATIVE_ROLE_ID,
    OTHER_NATIVE_ROLE_ID,
    SPANISH_NATIVE_ROLE_ID,
)
from config import get_int_env

# Optional private channel for the weekly stats report. Set to 0 to disable.
STATS_REPORT_CHANNEL_ID: int = get_int_env("STATS_REPORT_CHANNEL_ID", 0)
STATS_WEEKLY_REPORT_DAY: int = get_int_env("STATS_WEEKLY_REPORT_DAY", 0)
STATS_WEEKLY_REPORT_HOUR_UTC: int = get_int_env("STATS_WEEKLY_REPORT_HOUR_UTC", 9)

# Activity clock ($myclock): default whole-hour UTC offset for the hour-of-day
# labels. Whole-hour offsets stay exactly aligned to the stored UTC hour
# buckets, so no timezone database is needed. Default +1 (Europe/Madrid winter
# time); a caller can override per-invocation with the command's offset arg.
STATS_CLOCK_TZ_OFFSET: int = get_int_env("STATS_CLOCK_TZ_OFFSET", 1)


ROLE_MAP = {
    SPANISH_NATIVE_ROLE_ID: "spanish_native",
    ENGLISH_NATIVE_ROLE_ID: "english_native",
    OTHER_NATIVE_ROLE_ID: "other_native",
}

ROLE_LABELS = {
    "spanish_native": "Spanish Native",
    "english_native": "English Native",
    "other_native": "Other Native",
}

ROLE_COLORS = {
    "spanish_native": "#FF6B6B",
    "english_native": "#4ECDC4",
    "other_native": "#95A5A6",
}
