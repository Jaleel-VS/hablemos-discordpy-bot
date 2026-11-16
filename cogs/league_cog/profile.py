"""What ``/league profile`` shows: lifetime level and history plus this round."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from cogs.league_cog.levels import LevelProgress


@dataclass(frozen=True)
class RoundStanding:
    """A league member's place in the current round."""

    board: str  # 'spanish' or 'english'
    rank: int
    combined_rank: int
    points: int
    active_days: int
    bonus: int
    previous_rank: int | None  # final rank on this board last round; None if absent
    above_gap: int | None  # points to the member ranked just above; None at #1
    below_gap: int | None  # lead over the member just below; None if last

    @property
    def score(self) -> int:
        return self.points + self.bonus

    @property
    def movement(self) -> int:
        """Places climbed since last round (negative = dropped); 0 without a previous rank."""
        return 0 if self.previous_rank is None else self.previous_rank - self.rank


@dataclass(frozen=True)
class LeagueProfile:
    """Everything on a profile card, read once from the database."""

    progress: LevelProgress
    streak: int
    best_streak: int
    podiums: tuple[int, int, int]  # 1st, 2nd and 3rd place finishes
    champion_weeks: int
    best_round: int  # best completed-round score; 0 before the first
    daily_points: tuple[int, ...]  # last 7 UTC days, oldest first
    standing: RoundStanding | None  # None when not competing in the league


def effective_streak(streak: int, last_active: date | None, today: date) -> int:
    """The stored streak, or 0 once a whole UTC day has passed without activity."""
    if last_active is None or last_active < today - timedelta(days=1):
        return 0
    return streak
