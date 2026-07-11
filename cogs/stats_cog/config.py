"""Configuration for the stats cog."""

from config import get_int_env

# Only this guild is tracked and reported on (the main Hablemos server).
STATS_GUILD_ID: int = get_int_env("STATS_GUILD_ID", 243838819743432704)

# Optional private channel for the weekly stats report. Set to 0 to disable.
STATS_REPORT_CHANNEL_ID: int = get_int_env("STATS_REPORT_CHANNEL_ID", 0)
STATS_WEEKLY_REPORT_DAY: int = get_int_env("STATS_WEEKLY_REPORT_DAY", 0)
STATS_WEEKLY_REPORT_HOUR_UTC: int = get_int_env("STATS_WEEKLY_REPORT_HOUR_UTC", 9)

# Native role IDs for classification
SPANISH_NATIVE_ROLE_ID: int = get_int_env("STATS_SPANISH_NATIVE_ROLE", 243854128424550401)
ENGLISH_NATIVE_ROLE_ID: int = get_int_env("STATS_ENGLISH_NATIVE_ROLE", 243853718758359040)
OTHER_NATIVE_ROLE_ID: int = get_int_env("STATS_OTHER_NATIVE_ROLE", 247020385730691073)

# Role type labels
ROLE_MAP: dict[int, str] = {
    SPANISH_NATIVE_ROLE_ID: "spanish_native",
    ENGLISH_NATIVE_ROLE_ID: "english_native",
    OTHER_NATIVE_ROLE_ID: "other_native",
}

# Display labels for graphs
ROLE_LABELS: dict[str, str] = {
    "spanish_native": "Spanish Native",
    "english_native": "English Native",
    "other_native": "Other Native",
}

# Colors for graphs (role → hex)
ROLE_COLORS: dict[str, str] = {
    "spanish_native": "#FF6B6B",
    "english_native": "#4ECDC4",
    "other_native": "#95A5A6",
}
