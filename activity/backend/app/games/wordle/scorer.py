"""The Wordle letter-feedback algorithm.

Two passes over a ``Counter`` of the answer's letters — the only correct way to
handle duplicate letters (a single-pass "is this letter in the word" check is
the #1 clone bug):

1. First pass: exact-position matches ("green") claim a copy of that letter.
2. Second pass: remaining letters are "present" ("yellow") only while an
   unclaimed copy is left; otherwise "absent" ("gray").

Everything operates on normalized words (see :mod:`normalize`), so ñ is a
single letter throughout and accents are already stripped.
"""
from collections import Counter
from enum import StrEnum

from app.games.wordle.normalize import letters


class Tile(StrEnum):
    """Per-letter feedback state. String values ship directly to the client."""

    GREEN = "green"   # correct letter, correct position
    YELLOW = "yellow"  # correct letter, wrong position
    GRAY = "gray"     # letter not in the word (or no copies left)


def score(guess: str, answer: str) -> list[Tile]:
    """Return per-position feedback for ``guess`` against ``answer``.

    Both must be normalized and the same length; the caller guarantees this
    (guesses are validated before scoring).
    """
    g = letters(guess)
    a = letters(answer)
    result = [Tile.GRAY] * len(a)
    remaining = Counter(a)

    # Pass 1: greens claim their letter first.
    for i, ch in enumerate(g):
        if ch == a[i]:
            result[i] = Tile.GREEN
            remaining[ch] -= 1

    # Pass 2: yellows only while an unclaimed copy remains.
    for i, ch in enumerate(g):
        if result[i] is Tile.GREEN:
            continue
        if remaining.get(ch, 0) > 0:
            result[i] = Tile.YELLOW
            remaining[ch] -= 1

    return result


# Emoji used in the shareable result grid.
_EMOJI = {Tile.GREEN: "🟩", Tile.YELLOW: "🟨", Tile.GRAY: "⬛"}


def emoji_row(tiles: list[Tile]) -> str:
    """Render one scored row as its emoji string."""
    return "".join(_EMOJI[t] for t in tiles)
