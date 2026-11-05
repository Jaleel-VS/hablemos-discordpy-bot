"""
Configuration constants for the Language League system.

This module centralizes all magic numbers, IDs, and configuration values
used throughout the league cog to make them easy to find and modify.
"""

from dataclasses import dataclass
from typing import Final

from config import get_int_env, get_list_env

WINNER_CHANNEL_ID: Final[int] = get_int_env("LEAGUE_WINNER_CHANNEL_ID", 247135634265735168)

# Role given to weekly champions (top 3 eligible per league)
CHAMPION_ROLE_ID: Final[int] = get_int_env("LEAGUE_CHAMPION_ROLE_ID", 1062819085789970564)


@dataclass(frozen=True)
class ScoringConfig:
    """Configuration for the league scoring system."""

    POINTS_PER_MESSAGE: int = 1

    ACTIVE_DAY_BONUS_MULTIPLIER: int = 5

    TOP_WINNERS_COUNT: int = 3

    LEADERBOARD_DISPLAY_LIMIT: int = 10

SCORING = ScoringConfig()


# Channels where each counted message earns extra points. The multiplier
# is applied to ``SCORING.POINTS_PER_MESSAGE`` and rounded up, so at the
# current base of 1 pt/msg a beginner channel awards 2 pts/msg. Keep the
# multiplier itself (not a hardcoded +1 bonus) so the math still behaves
# if ``POINTS_PER_MESSAGE`` is ever bumped.
#
# The defaults are the server's beginner channels; override via the
# ``LEAGUE_BEGINNER_CHANNEL_IDS`` env var (comma-separated IDs) if the
# list needs tweaking without a redeploy.
_BEGINNER_CHANNEL_DEFAULTS: Final[list[str]] = [
    "1414221788765880330",
    "243858509123289089",
    "243858546746327050",
]
BEGINNER_CHANNEL_IDS: Final[frozenset[int]] = frozenset(
    int(cid) for cid in get_list_env(
        "LEAGUE_BEGINNER_CHANNEL_IDS", _BEGINNER_CHANNEL_DEFAULTS,
    )
)
BEGINNER_CHANNEL_MULTIPLIER: Final[float] = 1.25


@dataclass(frozen=True)
class RateLimitConfig:
    """Configuration for anti-spam and rate limiting."""

    MESSAGE_COOLDOWN_SECONDS: int = 30

    DAILY_MESSAGE_CAP: int = 200

    MIN_MESSAGE_LENGTH: int = 10

RATE_LIMITS = RateLimitConfig()


@dataclass(frozen=True)
class RoundConfig:
    """Configuration for league rounds."""

    ROUND_DURATION_DAYS: int = 7

    ROUND_CHECK_INTERVAL_MINUTES: int = 1

ROUNDS = RoundConfig()


@dataclass(frozen=True)
class LeagueDisplay:
    """Display strings for different league types."""

    SPANISH_EMOJI: str = "🇪🇸"
    ENGLISH_EMOJI: str = "🇬🇧"
    COMBINED_EMOJI: str = "🌍"

    SPANISH_NAME: str = "Spanish League"
    ENGLISH_NAME: str = "English League"
    COMBINED_NAME: str = "Combined League"

    def get_emoji(self, league_type: str) -> str:
        """Get emoji for league type."""
        return {
            'spanish': self.SPANISH_EMOJI,
            'english': self.ENGLISH_EMOJI,
            'combined': self.COMBINED_EMOJI
        }.get(league_type, self.COMBINED_EMOJI)

    def get_name(self, league_type: str) -> str:
        """Get display name for league type."""
        return {
            'spanish': self.SPANISH_NAME,
            'english': self.ENGLISH_NAME,
            'combined': self.COMBINED_NAME
        }.get(league_type, self.COMBINED_NAME)

DISPLAY = LeagueDisplay()

