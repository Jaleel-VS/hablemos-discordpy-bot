"""Configuration for the stats cog."""

from config import get_int_env

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
