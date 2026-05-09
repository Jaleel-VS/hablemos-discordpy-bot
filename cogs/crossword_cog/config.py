"""Configuration constants for the crossword cog."""
from dataclasses import dataclass
from typing import Final

# Game settings
GAME_TIMEOUT_SECONDS: Final[int] = 600  # 10 minutes
COMMAND_COOLDOWN_SECONDS: Final[int] = 10
WORDS_PER_GAME_MIN: Final[int] = 4
WORDS_PER_GAME_MAX: Final[int] = 6
MAX_PLACEMENT_ATTEMPTS: Final[int] = 200

# Word validation
MAX_WORD_LENGTH: Final[int] = 13
MIN_WORD_LENGTH: Final[int] = 3
MAX_GUESS_LENGTH: Final[int] = 50
MIN_GUESS_LENGTH: Final[int] = 2

# Timeout watcher
TIMEOUT_CHECK_INTERVAL: Final[int] = 30  # Check every 30 seconds

# Grid generation
GRID_REDUCE_THRESHOLD: Final[int] = 20  # Attempts before reducing word count
GRID_REDUCE_INTERVAL: Final[int] = 10   # How often to reduce after threshold


@dataclass(frozen=True)
class DifficultyConfig:
    """Settings per difficulty level."""

    name: str
    reveal_fraction: float  # fraction of letters to pre-reveal
    label: str


DIFFICULTIES: dict[str, DifficultyConfig] = {
    "beginner": DifficultyConfig(
        name="beginner",
        reveal_fraction=0.3,
        label="🟢 Beginner",
    ),
    "advanced": DifficultyConfig(
        name="advanced",
        reveal_fraction=0.0,
        label="🔴 Advanced",
    ),
}

DEFAULT_DIFFICULTY: Final[str] = "beginner"
DEFAULT_LANGUAGE: Final[str] = "es"
