"""Unit tests for the pure streak/distribution logic (no DB required)."""
from app.db import compute_streak, distribution_key


def test_first_win_starts_streak():
    assert compute_streak(prev_streak=0, last_puzzle_no=None, won=True, puzzle_no=10) == 1


def test_consecutive_win_extends():
    assert compute_streak(prev_streak=3, last_puzzle_no=10, won=True, puzzle_no=11) == 4


def test_gap_resets_to_one():
    # Missed a day: puzzle 13 after last 10 -> streak restarts at 1.
    assert compute_streak(prev_streak=3, last_puzzle_no=10, won=True, puzzle_no=13) == 1


def test_loss_resets_to_zero():
    assert compute_streak(prev_streak=5, last_puzzle_no=10, won=False, puzzle_no=11) == 0


def test_distribution_key_win():
    assert distribution_key(won=True, guesses_used=4) == "4"


def test_distribution_key_loss():
    assert distribution_key(won=False, guesses_used=6) == "X"
    assert distribution_key(won=True, guesses_used=None) == "X"
