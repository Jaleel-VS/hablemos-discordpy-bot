"""Tests for CrosswordGame.use_hint.

Covers the two-hints-per-game cap, the 'no hidden cells' exit, and the
interaction between solved words and the hint-eligibility set.
"""
from __future__ import annotations

import random

from .conftest import build_game


def test_each_hint_reveals_a_new_letter() -> None:
    random.seed(7)
    game = build_game()
    previous = game.render().fp.getvalue()
    for _ in range(2):
        result = game.use_hint()
        assert result.success
        assert result.word in {game.get_answer(i) for i in range(len(game.grid.placed))}
        assert result.reason is None
        current = game.render().fp.getvalue()
        assert current != previous
        previous = current


def test_third_hint_blocked() -> None:
    random.seed(7)
    game = build_game()
    game.use_hint()
    game.use_hint()
    result = game.use_hint()
    assert result.success is False
    assert result.reason == "max_hints_reached"
    assert result.word is None


def test_hint_on_all_solved_reports_no_hidden_cells() -> None:
    random.seed(7)
    game = build_game()
    for i in range(len(game.grid.placed)):
        game.solved.add(i)
    result = game.use_hint()
    assert result.success is False
    assert result.reason == "no_hidden_cells"
    assert game.hints_used == 0


