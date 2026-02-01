"""
Configuration constants for the Language League system.

This module centralizes all magic numbers, IDs, and configuration values
used throughout the league cog to make them easy to find and modify.
"""

from dataclasses import dataclass
from typing import Final


# =============================================================================
# DISCORD SERVER CONFIGURATION
# =============================================================================

# Guild ID - Language League is only available in this server
LEAGUE_GUILD_ID: Final[int] = 243838819743432704

# Channel where round winners are announced
WINNER_CHANNEL_ID: Final[int] = 247135634265735168

# Role given to weekly champions (top 3 eligible per league)
CHAMPION_ROLE_ID: Final[int] = 1062819085789970564


# =============================================================================
# ROLE IDS
# =============================================================================

@dataclass(frozen=True)
class RoleIDs:
    """Discord role IDs for language learning roles."""

    # Native speaker roles
    ENGLISH_NATIVE: int = 243853718758359040
    SPANISH_NATIVE: int = 243854128424550401
    OTHER_NATIVE: int = 247020385730691073

    # Language learner roles
    LEARNING_SPANISH: int = 297415063302832128
    LEARNING_ENGLISH: int = 247021017740869632


# Instantiate as a constant for easy access
ROLES = RoleIDs()


# =============================================================================
# SCORING SYSTEM
# =============================================================================

@dataclass(frozen=True)
class ScoringConfig:
    """Configuration for the league scoring system."""

    # Points awarded per valid message
    POINTS_PER_MESSAGE: int = 1

    # Bonus points multiplier for each active day
    ACTIVE_DAY_BONUS_MULTIPLIER: int = 5

    # How many top users to track as winners
    TOP_WINNERS_COUNT: int = 3

    # How many users to show in leaderboard image
    LEADERBOARD_DISPLAY_LIMIT: int = 10


# Instantiate as a constant
SCORING = ScoringConfig()


# =============================================================================
# ANTI-SPAM / RATE LIMITING
# =============================================================================

@dataclass(frozen=True)
class RateLimitConfig:
    """Configuration for anti-spam and rate limiting."""

    # Cooldown between counted messages in the same channel (seconds)
    MESSAGE_COOLDOWN_SECONDS: int = 60  # 1 minute

    # Maximum messages that count toward score per day
    DAILY_MESSAGE_CAP: int = 100

    # Minimum message length to count (characters)
    MIN_MESSAGE_LENGTH: int = 10


# Instantiate as a constant
RATE_LIMITS = RateLimitConfig()


# =============================================================================
# ROUND CONFIGURATION
# =============================================================================

@dataclass(frozen=True)
class RoundConfig:
    """Configuration for league rounds."""

    # Duration of each round in days
    ROUND_DURATION_DAYS: int = 7  # 1 week

    # How often to check if round should end (minutes)
    ROUND_CHECK_INTERVAL_MINUTES: int = 1


# Instantiate as a constant
ROUNDS = RoundConfig()


# =============================================================================
# LEAGUE NAMES AND DISPLAY
# =============================================================================

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


# Instantiate as a constant
DISPLAY = LeagueDisplay()


# =============================================================================
# LANGUAGE DETECTION
# =============================================================================

@dataclass(frozen=True)
class LanguageConfig:
    """Configuration for language detection."""

    # Language codes
    SPANISH_CODE: str = 'es'
    ENGLISH_CODE: str = 'en'

    # Seed for consistent langdetect results
    LANGDETECT_SEED: int = 0


# Instantiate as a constant
LANGUAGE = LanguageConfig()
