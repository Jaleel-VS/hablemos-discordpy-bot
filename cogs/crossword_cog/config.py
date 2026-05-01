"""Configuration constants for the crossword cog."""
from dataclasses import dataclass
from typing import Final

# Game settings
GAME_TIMEOUT_SECONDS: Final[int] = 300  # 5 minutes
COMMAND_COOLDOWN_SECONDS: Final[int] = 10
WORDS_PER_GAME: Final[int] = 5
MAX_PLACEMENT_ATTEMPTS: Final[int] = 200


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
