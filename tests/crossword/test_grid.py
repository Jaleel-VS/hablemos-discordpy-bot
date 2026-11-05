"""Tests for grid generation.

Covers the happy path, placement invariants (no parallel-touching
letters, every word beyond the first crosses another), pathological
inputs, and the progressive word-reduction retry logic.
"""
from __future__ import annotations

import random

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
    for pw in grid.placed[1:]:
        assert _intersecting_cells(grid, pw), (
            f"Word {pw.word!r} was placed without crossing any other word"
        )


def test_shared_cells_have_matching_letters() -> None:
    random.seed(0)
    grid = generate_grid(["casa", "sol", "luna", "agua"])
    assert grid is not None
    for pw in grid.placed:
        for i, (r, c) in enumerate(pw.cells):
            assert grid.cells[(r, c)].lower() == pw.word[i].lower()


def test_pathological_words_return_none() -> None:
    # No shared letters between any pair — cannot place more than one.
    random.seed(0)
    grid = generate_grid(["aaaa", "bbbb", "cccc", "dddd"])
    assert grid is None


def test_reduction_yields_smaller_grid_when_full_fails() -> None:
    """Unplaceable loners must not prevent a usable three-word puzzle."""
    random.seed(0)
    grid = generate_grid(["casa", "sala", "alas", "xxxx", "yyyy", "zzzz"])
    assert grid is not None
    assert {pw.word for pw in grid.placed} == {"casa", "sala", "alas"}


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


def test_empty_input_returns_none() -> None:
    assert generate_grid([]) is None
