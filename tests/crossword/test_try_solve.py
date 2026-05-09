"""Tests for CrosswordGame.try_solve.

Covers input validation bounds, accent-insensitive matching, already-
solved words, and the SolveAttempt return shape.
"""
from __future__ import annotations

from cogs.crossword_cog.config import MAX_GUESS_LENGTH, MIN_GUESS_LENGTH

from .conftest import build_game, make_entry


def test_correct_answer_matches() -> None:
    game = build_game()
    # Pick whichever word the grid placed first — we know it was placed.
    answer = game.grid.placed[0].word
    attempt = game.try_solve(answer)
    assert attempt.is_valid_guess
    assert attempt.matched_idx is not None


def test_accent_insensitive_match() -> None:
    entries = [
        make_entry("cancion", "song"),
        make_entry("sol", "sun"),
        make_entry("nuez", "nut"),  # shares letters → placeable
    ]
    game = build_game(entries)
    # Typing the accented form should still match the unaccented stored form.
    attempt = game.try_solve("Canción")
    assert attempt.is_valid_guess
    assert attempt.matched_idx is not None
    assert game.get_answer(attempt.matched_idx) == "cancion"


def test_wrong_answer_returns_none_but_is_valid() -> None:
    game = build_game()
    attempt = game.try_solve("xylophone")
    assert attempt.is_valid_guess
    assert attempt.matched_idx is None


def test_already_solved_word_does_not_match_again() -> None:
    game = build_game()
    answer = game.grid.placed[0].word
    first = game.try_solve(answer)
    assert first.matched_idx == 0
    # Simulate the on_message path marking it solved.
    game.solved.add(0)
    second = game.try_solve(answer)
    assert second.is_valid_guess
    assert second.matched_idx is None


def test_too_short_is_invalid() -> None:
    game = build_game()
    attempt = game.try_solve("a" * (MIN_GUESS_LENGTH - 1))
    assert not attempt.is_valid_guess
    assert attempt.matched_idx is None


def test_too_long_is_invalid() -> None:
    game = build_game()
    attempt = game.try_solve("a" * (MAX_GUESS_LENGTH + 1))
    assert not attempt.is_valid_guess


def test_only_punctuation_is_invalid() -> None:
    game = build_game()
    attempt = game.try_solve("!!!???")
    # Passes the length check but normalizes to "" → flagged invalid.
    assert not attempt.is_valid_guess


def test_solve_attempt_is_frozen() -> None:
    game = build_game()
    attempt = game.try_solve("casa")
    # Confirms the dataclass migration stayed frozen — prevents accidental
    # mutation in callers.
    import dataclasses
    assert dataclasses.is_dataclass(attempt)
    try:
        attempt.matched_idx = 99  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        pass
    else:
        raise AssertionError("SolveAttempt should be frozen")
