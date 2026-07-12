"""Daily-secret selection for Wordle.

The daily word is deterministic by date so everyone gets the same puzzle and a
stable puzzle number for the shareable "Wordle #NNN" header. Free-play draws a
random secret instead.
"""
from datetime import date

from app.games.wordle.words import ANSWERS

# Puzzle #1 corresponds to this date. Chosen as the launch epoch; changing it
# renumbers every puzzle, so it is fixed once shipped.
_EPOCH = date(2026, 1, 1)


def puzzle_number(today: date) -> int:
    """1-based puzzle number for a given date (>= 1)."""
    return (today - _EPOCH).days + 1


def daily_index(today: date) -> int:
    """Index into ANSWERS for the given date, wrapping over the list."""
    return (today - _EPOCH).days % len(ANSWERS)


def daily_answer(today: date) -> tuple[str, int]:
    """Return ``(answer, puzzle_number)`` for the given date."""
    return ANSWERS[daily_index(today)], puzzle_number(today)
