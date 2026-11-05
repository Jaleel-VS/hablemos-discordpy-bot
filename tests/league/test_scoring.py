"""Tests for cogs.league_cog.scoring.

Confirms that the beginner-channel multiplier is applied with
ceiling rounding and that non-beginner channels fall through to the
base points unchanged.
"""
from __future__ import annotations

from dataclasses import replace
from unittest.mock import patch

import pytest

from cogs.league_cog.config import (
    BEGINNER_CHANNEL_IDS,
    BEGINNER_CHANNEL_MULTIPLIER,
    SCORING,
)
from cogs.league_cog.scoring import get_channel_multiplier, points_for_message


def test_multiplier_for_non_beginner_channel_is_one() -> None:
    assert get_channel_multiplier(0) == 1.0
    assert get_channel_multiplier(99_999_999_999) == 1.0


def test_multiplier_for_beginner_channel() -> None:
    sample = next(iter(BEGINNER_CHANNEL_IDS))
    assert get_channel_multiplier(sample) == BEGINNER_CHANNEL_MULTIPLIER


def test_points_for_message_non_beginner_uses_base() -> None:
    assert points_for_message(0) == SCORING.POINTS_PER_MESSAGE


def test_points_for_message_beginner_doubles_at_base_1() -> None:
    """At the current base of 1 pt/msg, ceil(1 * 1.25) == 2."""
    sample = next(iter(BEGINNER_CHANNEL_IDS))
    assert points_for_message(sample) == 2


@pytest.mark.parametrize(
    ("base", "multiplier", "expected"),
    [
        (1, 1.0, 1),
        (1, 1.25, 2),
        (2, 1.25, 3),
        (4, 1.25, 5),
        (10, 1.5, 15),
        (3, 1.0, 3),
    ],
)
def test_message_points_round_up(base: int, multiplier: float, expected: int) -> None:
    """Counted messages use ceiling rounding, including after base changes."""
    sample = next(iter(BEGINNER_CHANNEL_IDS))
    scoring = replace(SCORING, POINTS_PER_MESSAGE=base)
    with (
        patch("cogs.league_cog.scoring.SCORING", scoring),
        patch("cogs.league_cog.scoring.BEGINNER_CHANNEL_MULTIPLIER", multiplier),
    ):
        assert points_for_message(sample) == expected


def test_beginner_ids_are_ints_not_strings() -> None:
    # The env loader returns strings; ``config.py`` must cast to int.
    # If this regresses, ``channel.id in BEGINNER_CHANNEL_IDS`` silently
    # returns False for every real Discord channel ID.
    for cid in BEGINNER_CHANNEL_IDS:
        assert isinstance(cid, int)


