"""Language League levels: the XP curve, level-up detection and background tiers.

XP is league points earned since levels launched; ``db.leaderboard`` adds a
message's points to the member's XP in the same transaction that records it.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cogs.league_cog.config import LEVELS


def xp_for_level(level: int) -> int:
    """Total XP needed to reach ``level``. Level 1 needs none."""
    if level <= 1:
        return 0
    return round(LEVELS.BASE * (level - 1) ** LEVELS.EXPONENT)


def level_for_xp(xp: int) -> int:
    """The level a member with ``xp`` total XP is at."""
    if xp <= 0:
        return 1
    level = int((xp / LEVELS.BASE) ** (1 / LEVELS.EXPONENT)) + 1
    # The float estimate can be one off either way at level boundaries.
    while xp_for_level(level + 1) <= xp:
        level += 1
    while xp_for_level(level) > xp:
        level -= 1
    return level


@dataclass(frozen=True)
class LevelProgress:
    """Where a member stands within their current level."""

    xp: int
    level: int
    level_start: int
    next_level_at: int

    @property
    def to_next(self) -> int:
        """XP still needed for the next level."""
        return self.next_level_at - self.xp

    @property
    def fraction(self) -> float:
        """Share of the current level completed, from 0 to 1."""
        return (self.xp - self.level_start) / (self.next_level_at - self.level_start)


def progress_for_xp(xp: int) -> LevelProgress:
    """Level and progress toward the next level for ``xp`` total XP."""
    xp = max(0, xp)
    level = level_for_xp(xp)
    return LevelProgress(
        xp=xp,
        level=level,
        level_start=xp_for_level(level),
        next_level_at=xp_for_level(level + 1),
    )


@dataclass(frozen=True)
class XpGain:
    """A member's XP before and after one counted message."""

    xp_before: int
    xp_after: int
    cards_enabled: bool

    @property
    def old_level(self) -> int:
        return level_for_xp(self.xp_before)

    @property
    def new_level(self) -> int:
        return level_for_xp(self.xp_after)

    @property
    def leveled_up(self) -> bool:
        return self.new_level > self.old_level


BACKGROUND_DIR = Path(__file__).parent / "league_helper" / "level_backgrounds"


@dataclass(frozen=True)
class Tier:
    """A band of levels that shares a card background."""

    name: str
    min_level: int

    @property
    def background(self) -> Path:
        return BACKGROUND_DIR / f"{self.name.lower()}.jpg"


# Ascending by ``min_level``; the first tier must start at level 1.
TIERS: tuple[Tier, ...] = (
    Tier("Dawn", 1),
    Tier("Mist", 10),
    Tier("Lilac", 25),
    Tier("Tide", 50),
    Tier("Bloom", 75),
    Tier("Gold", 100),
)


def tier_for_level(level: int) -> Tier:
    """The tier whose background a card at ``level`` uses."""
    current = TIERS[0]
    for tier in TIERS:
        if level >= tier.min_level:
            current = tier
    return current
