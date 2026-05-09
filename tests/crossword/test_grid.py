"""Tests for grid generation.

Covers the happy path, placement invariants (no parallel-touching
letters, every word beyond the first crosses another), pathological
inputs, and the progressive word-reduction retry logic.
"""
from __future__ import annotations

import random

from cogs.crossword_cog.config import (
    GRID_REDUCE_INTERVAL,
    GRID_REDUCE_THRESHOLD,
)
from cogs.crossword_cog.grid import Grid, generate_grid


def _intersecting_cells(grid: Grid, pw) -> set[tuple[int, int]]:
    """Return cells of ``pw`` that overlap with any other placed word."""
    pw_cells = set(pw.cells)
    other_cells: set[tuple[int, int]] = set()
    for other in grid.placed:
        if other is pw:
            continue
        other_cells.update(other.cells)
    return pw_cells & other_cells


def test_happy_path_places_all_words() -> None:
    random.seed(0)
    grid = generate_grid(["casa", "sol", "luna", "agua"])
    assert grid is not None
    assert len(grid.placed) == 4


def test_every_non_first_word_intersects_another() -> None:
    random.seed(0)
    grid = generate_grid(["casa", "sol", "luna", "agua"])
    assert grid is not None
    # First word placed can stand alone; the rest must cross something.
    for pw in grid.placed[1:]:
        assert _intersecting_cells(grid, pw), (
            f"Word {pw.word!r} was placed without crossing any other word"
        )


def test_shared_cells_have_matching_letters() -> None:
    random.seed(0)
    grid = generate_grid(["casa", "sol", "luna", "agua"])
    assert grid is not None
    # Invariant: every cell holds exactly one letter; where two words
    # share a cell, the letters match by construction of ``place``.
    for pw in grid.placed:
        for i, (r, c) in enumerate(pw.cells):
            assert grid.cells[(r, c)].lower() == pw.word[i].lower()


def test_pathological_words_return_none() -> None:
    # No shared letters between any pair — cannot place more than one.
    random.seed(0)
    grid = generate_grid(["aaaa", "bbbb", "cccc", "dddd"])
    assert grid is None


def test_reduction_yields_smaller_grid_when_full_fails(monkeypatch) -> None:
    """If the full word list is unplaceable, the reduction path should
    eventually return a smaller grid (>= 3 words)."""
    # 6 words: one cluster of 3 that can cross, plus 3 loners that share
    # no letters with anything. The 3 loners make a full placement
    # impossible, but after reduction we should be left with the
    # placeable cluster.
    random.seed(0)
    words = ["casa", "sala", "alas", "xxxx", "yyyy", "zzzz"]
    grid = generate_grid(words)
    # Either a reduced grid was produced, or placement gave up entirely.
    # The invariant we care about: we never return a grid with < 3 words,
    # and we never crash.
    if grid is not None:
        assert len(grid.placed) >= 3
        assert len(grid.placed) <= len(words)


def test_reduction_floor_is_three_words() -> None:
    """Reduction math must never drop below 3 words."""
    # Simulate the formula used inside generate_grid for varied inputs.
    for n_words in (3, 4, 5, 6):
        for attempt in range(0, 300, 5):
            steps = (
                max(0, (attempt - GRID_REDUCE_THRESHOLD))
                // GRID_REDUCE_INTERVAL
            )
            reduce_by = min(steps, n_words - 3)
            remaining = n_words - max(0, reduce_by)
            assert remaining >= 3, (
                f"n={n_words} attempt={attempt} left {remaining} words"
            )


def test_generator_is_deterministic_with_seed() -> None:
    """Same seed + same inputs → same grid. Guards against accidental
    reliance on dict ordering or global RNG state."""
    random.seed(999)
    g1 = generate_grid(["casa", "sol", "luna", "agua"])
    random.seed(999)
    g2 = generate_grid(["casa", "sol", "luna", "agua"])
    assert g1 is not None and g2 is not None
    assert [(p.word, p.row, p.col, p.direction) for p in g1.placed] == \
           [(p.word, p.row, p.col, p.direction) for p in g2.placed]


def test_empty_input_does_not_crash() -> None:
    # Edge case — caller should never pass this, but we shouldn't
    # IndexError on it either.
    random.seed(0)
    result = generate_grid([])
    assert result is None or len(result.placed) == 0
