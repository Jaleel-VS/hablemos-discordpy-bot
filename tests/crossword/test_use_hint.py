"""Tests for CrosswordGame.use_hint.

Covers the two-hints-per-game cap, the 'no hidden cells' exit, and the
interaction between solved words and the hint-eligibility set.
"""
from __future__ import annotations

import random

from .conftest import build_game


def test_first_hint_succeeds() -> None:
    random.seed(7)
    game = build_game()
    result = game.use_hint()
    assert result.success is True
    assert result.word is not None
    assert result.reason is None
    assert game.hints_used == 1


def test_second_hint_succeeds() -> None:
    random.seed(7)
    game = build_game()
    game.use_hint()
    result = game.use_hint()
    assert result.success is True
    assert game.hints_used == 2


def test_third_hint_blocked() -> None:
    random.seed(7)
    game = build_game()
    game.use_hint()
    game.use_hint()
    result = game.use_hint()
    assert result.success is False
    assert result.reason == "max_hints_reached"
    assert game.hints_used == 2  # unchanged


def test_hint_on_all_solved_reports_no_hidden_cells() -> None:
    random.seed(7)
    game = build_game()
    # Mark every word as solved — all cells are now visible.
    for i in range(len(game.grid.placed)):
        game.solved.add(i)
    result = game.use_hint()
    assert result.success is False
    assert result.reason == "no_hidden_cells"
    assert game.hints_used == 0


def test_hint_records_word_index() -> None:
    random.seed(7)
    game = build_game()
    result = game.use_hint()
    assert result.success
    # Exactly one word should be flagged as having received a hint.
    assert len(game.word_hints) == 1
    # And the returned word should match one of the unsolved answers.
    all_answers = {game.get_answer(i) for i in range(len(game.grid.placed))}
    assert result.word in all_answers


def test_hint_reveals_a_cell_in_the_grid() -> None:
    random.seed(7)
    game = build_game()
    before = dict(game.revealed_cells)
    result = game.use_hint()
    assert result.success
    # At least one new cell was revealed.
    assert len(game.revealed_cells) == len(before) + 1
