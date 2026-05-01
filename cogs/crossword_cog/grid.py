"""Crossword grid generation via backtracking.

Places words on a 2D grid so they intersect at shared letters.
The first word is placed horizontally in the center; subsequent words
alternate direction and must cross an already-placed word.
"""
from __future__ import annotations

import random
import unicodedata
from dataclasses import dataclass, field

from .config import MAX_PLACEMENT_ATTEMPTS


@dataclass(frozen=True)
class PlacedWord:
    """A word placed on the grid."""

    word: str
    row: int
    col: int
    direction: str  # "across" or "down"
    number: int

    @property
    def cells(self) -> list[tuple[int, int]]:
        """Return all (row, col) cells this word occupies."""
        dr, dc = (0, 1) if self.direction == "across" else (1, 0)
        return [(self.row + dr * i, self.col + dc * i) for i in range(len(self.word))]


def _normalize(char: str) -> str:
    """Strip accents for grid matching (á → a)."""
    nfkd = unicodedata.normalize("NFKD", char.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


@dataclass
class Grid:
    """Sparse crossword grid."""

    cells: dict[tuple[int, int], str] = field(default_factory=dict)
    placed: list[PlacedWord] = field(default_factory=list)
    _next_number: int = 1
    _cell_numbers: dict[tuple[int, int], int] = field(default_factory=dict)

    def _fits(self, word: str, row: int, col: int, direction: str) -> bool:
        """Check if *word* can be placed at (row, col) in *direction*."""
        dr, dc = (0, 1) if direction == "across" else (1, 0)

        # Check cell before the word is empty (no adjacent word bleeding in)
        before = (row - dr, col - dc)
        if before in self.cells:
            return False

        # Check cell after the word is empty
        after = (row + dr * len(word), col + dc * len(word))
        if after in self.cells:
            return False

        has_intersection = False
        for i, ch in enumerate(word):
            r, c = row + dr * i, col + dc * i
            norm_ch = _normalize(ch)

            if (r, c) in self.cells:
                # Must match existing letter
                if _normalize(self.cells[(r, c)]) != norm_ch:
                    return False
                has_intersection = True
            else:
                # Check perpendicular neighbors are empty (avoid parallel touching)
                perp = [(r + dc, c + dr), (r - dc, c - dr)]
                for pr, pc in perp:
                    if (pr, pc) in self.cells and not any(
                        (pr, pc) in set(pw.cells) and (r, c) in set(pw.cells)
                        for pw in self.placed
                    ):
                        return False

        # First word doesn't need an intersection
        return not (self.placed and not has_intersection)

    def place(self, word: str, row: int, col: int, direction: str) -> PlacedWord:
        """Place a word on the grid. Caller must verify _fits() first."""
        start = (row, col)
        if start in self._cell_numbers:
            number = self._cell_numbers[start]
        else:
            number = self._next_number
            self._cell_numbers[start] = number
            self._next_number += 1

        pw = PlacedWord(
            word=word, row=row, col=col,
            direction=direction, number=number,
        )
        for r, c in pw.cells:
            self.cells[(r, c)] = word[pw.cells.index((r, c))]
        self.placed.append(pw)
        return pw

    @property
    def bounds(self) -> tuple[int, int, int, int]:
        """Return (min_row, min_col, max_row, max_col)."""
        if not self.cells:
            return (0, 0, 0, 0)
        rows = [r for r, _ in self.cells]
        cols = [c for _, c in self.cells]
        return (min(rows), min(cols), max(rows), max(cols))


def _find_placements(
    grid: Grid, word: str, direction: str,
) -> list[tuple[int, int]]:
    """Find all valid positions for *word* crossing existing words."""
    candidates: list[tuple[int, int]] = []
    norm_word = [_normalize(ch) for ch in word]

    for pw in grid.placed:
        if pw.direction == direction:
            continue  # Need opposite direction to cross
        for pi, (pr, pc) in enumerate(pw.cells):
            existing_ch = _normalize(pw.word[pi])
            for wi, wch in enumerate(norm_word):
                if wch == existing_ch:
                    if direction == "across":
                        r, c = pr, pc - wi
                    else:
                        r, c = pr - wi, pc
                    if grid._fits(word, r, c, direction):
                        candidates.append((r, c))
    return candidates


def generate_grid(words: list[str]) -> Grid | None:
    """Generate a crossword grid for the given words.

    Returns None if placement fails.  Words should be uppercase or
    lowercase — accents are handled internally.
    """
    if not words:
        return None

    # Sort longest first for better placement
    ordered = sorted(enumerate(words), key=lambda t: -len(t[1]))
    original_indices = [i for i, _ in ordered]
    sorted_words = [w for _, w in ordered]

    for _ in range(MAX_PLACEMENT_ATTEMPTS):
        grid = Grid()

        # Place first word horizontally at origin
        first = sorted_words[0]
        grid.place(first, 0, 0, "across")

        success = True
        for idx in range(1, len(sorted_words)):
            word = sorted_words[idx]
            # Alternate preferred direction
            preferred = "down" if idx % 2 == 1 else "across"
            alt = "across" if preferred == "down" else "down"

            candidates = _find_placements(grid, word, preferred)
            if not candidates:
                candidates = _find_placements(grid, word, alt)
                preferred = alt

            if not candidates:
                success = False
                break

            r, c = random.choice(candidates)
            grid.place(word, r, c, preferred)

        if success:
            return grid

        # Shuffle and retry
        combined = list(zip(sorted_words[1:], original_indices[1:], strict=True))
        random.shuffle(combined)
        sorted_words[1:] = [w for w, _ in combined]
        original_indices[1:] = [i for _, i in combined]

    return None
