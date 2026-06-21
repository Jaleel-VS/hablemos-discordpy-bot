"""Vocab Catch cog configuration.

Three spawn channels, each with a learner-direction **mode** plus its own
rarity weights. A card prompt is rendered in one language and caught by
typing the other (or the same word, for the neutral General channel).

Modes:
- ``es_to_en`` — show the Spanish word, catch by typing the English word
  (Spanish speakers learning English → the Beginner-ES channel).
- ``en_to_es`` — show the English word, catch by typing the Spanish word
  (English speakers learning Spanish → the Beginner-EN channel).
- ``show_es``  — show the Spanish word, catch by typing it as shown
  (neutral General channel).

All env-driven values use the shared helpers in the top-level ``config``.
"""
from config import get_int_env

# ── Spawn channels (0 disables that channel) ──
# English-speakers' beginner channel: prompt in English, answer in Spanish.
VOCATCH_BEGINNER_EN_CHANNEL_ID: int = get_int_env("VOCATCH_BEGINNER_EN_CHANNEL_ID", 0)
# Spanish-speakers' beginner channel: prompt in Spanish, answer in English.
VOCATCH_BEGINNER_ES_CHANNEL_ID: int = get_int_env("VOCATCH_BEGINNER_ES_CHANNEL_ID", 0)
# General channel: prompt in Spanish, catch by typing the Spanish word.
VOCATCH_GENERAL_CHANNEL_ID: int = get_int_env("VOCATCH_GENERAL_CHANNEL_ID", 0)

# Per-channel mode. Keys are channel ids resolved at cog init.
MODE_EN_TO_ES = "en_to_es"
MODE_ES_TO_EN = "es_to_en"
MODE_SHOW_ES = "show_es"

# ── Spawn pacing (shared across channels) ──
VOCATCH_SPAWN_EVERY: int = get_int_env("VOCATCH_SPAWN_EVERY", 25)
VOCATCH_SPAWN_JITTER: int = get_int_env("VOCATCH_SPAWN_JITTER", 10)
VOCATCH_SPAWN_COOLDOWN_S: int = get_int_env("VOCATCH_SPAWN_COOLDOWN_S", 120)
VOCATCH_DESPAWN_S: int = get_int_env("VOCATCH_DESPAWN_S", 300)

# ── Rarity weights per channel kind ──
# All channels can spawn every rarity tier; beginner channels skew commoner
# (a Legendary is still possible, just rarer). General has the steeper
# "more rares show up" curve.
BEGINNER_RARITY_WEIGHTS: dict[int, int] = {1: 70, 2: 20, 3: 7, 4: 2, 5: 1}
GENERAL_RARITY_WEIGHTS: dict[int, int] = {1: 45, 2: 27, 3: 18, 4: 7, 5: 3}

# Points awarded per catch, by rarity tier (shared across channels).
RARITY_POINTS: dict[int, int] = {1: 1, 2: 3, 3: 8, 4: 15, 5: 25}

RARITY_LABELS: dict[int, str] = {
    1: "Common", 2: "Uncommon", 3: "Rare", 4: "Epic", 5: "Legendary",
}
RARITY_EMBED_COLORS: dict[int, int] = {
    1: 0x94A3B8, 2: 0x34D399, 3: 0x60A5FA, 4: 0xC084FC, 5: 0xFBBF24,
}


def channel_modes() -> dict[int, str]:
    """Map each configured channel id to its mode (skips disabled 0s)."""
    out: dict[int, str] = {}
    if VOCATCH_BEGINNER_EN_CHANNEL_ID:
        out[VOCATCH_BEGINNER_EN_CHANNEL_ID] = MODE_EN_TO_ES
    if VOCATCH_BEGINNER_ES_CHANNEL_ID:
        out[VOCATCH_BEGINNER_ES_CHANNEL_ID] = MODE_ES_TO_EN
    if VOCATCH_GENERAL_CHANNEL_ID:
        out[VOCATCH_GENERAL_CHANNEL_ID] = MODE_SHOW_ES
    return out


def weights_for_mode(mode: str) -> dict[int, int]:
    """Rarity weights for a channel mode (General steeper, beginners flatter)."""
    return GENERAL_RARITY_WEIGHTS if mode == MODE_SHOW_ES else BEGINNER_RARITY_WEIGHTS


__all__ = [
    "BEGINNER_RARITY_WEIGHTS",
    "GENERAL_RARITY_WEIGHTS",
    "MODE_EN_TO_ES",
    "MODE_ES_TO_EN",
    "MODE_SHOW_ES",
    "RARITY_EMBED_COLORS",
    "RARITY_LABELS",
    "RARITY_POINTS",
    "VOCATCH_BEGINNER_EN_CHANNEL_ID",
    "VOCATCH_BEGINNER_ES_CHANNEL_ID",
    "VOCATCH_DESPAWN_S",
    "VOCATCH_GENERAL_CHANNEL_ID",
    "VOCATCH_SPAWN_COOLDOWN_S",
    "VOCATCH_SPAWN_EVERY",
    "VOCATCH_SPAWN_JITTER",
    "channel_modes",
    "weights_for_mode",
]
