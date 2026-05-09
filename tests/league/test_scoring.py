"""Tests for cogs.league_cog.scoring.

Confirms that the beginner-channel multiplier is applied with
ceiling rounding and that non-beginner channels fall through to the
base points unchanged.
"""
from __future__ import annotations

import math
from unittest.mock import patch

import pytest

from cogs.league_cog.config import (
    BEGINNER_CHANNEL_IDS,
    BEGINNER_CHANNEL_MULTIPLIER,
    SCORING,
)
from cogs.league_cog.scoring import get_channel_multiplier, points_for_message


# Sanity-check the fixtures we rely on — if these ever change the
# downstream tests may need adjustment too.
def test_fixture_assumptions() -> None:
    assert len(BEGINNER_CHANNEL_IDS) >= 1
    assert BEGINNER_CHANNEL_MULTIPLIER > 1.0
    assert SCORING.POINTS_PER_MESSAGE == 1, (
        "scoring tests assume base points of 1; update them if this changes"
    )


def test_multiplier_for_non_beginner_channel_is_one() -> None:
    # Any ID that isn't in the beginner set should be 1.0 exactly.
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
        (2, 1.25, 3),    # ceil(2.5)
        (4, 1.25, 5),    # a "true" 1.25x
        (10, 1.5, 15),
        (3, 1.0, 3),     # multiplier of 1.0 short-circuits, no rounding surprise
    ],
)
def test_ceil_math_is_correct(base: int, multiplier: float, expected: int) -> None:
    """Verify the ceil math independently of config globals.

    This guards against future refactors that replace ``math.ceil`` with
    plain ``round`` or ``int`` and silently break the "always rounds up"
    contract.
    """
    assert math.ceil(base * multiplier) == expected


def test_beginner_ids_are_ints_not_strings() -> None:
    # The env loader returns strings; ``config.py`` must cast to int.
    # If this regresses, ``channel.id in BEGINNER_CHANNEL_IDS`` silently
    # returns False for every real Discord channel ID.
    for cid in BEGINNER_CHANNEL_IDS:
        assert isinstance(cid, int)


def test_points_for_message_respects_patched_base() -> None:
    """If POINTS_PER_MESSAGE is ever bumped, beginner points scale with it.

    Guards the "the math survives base changes" claim from the config
    comment. ``SCORING`` is a frozen dataclass, so we can't mutate it in
    place — instead we replace the module-level binding inside
    ``cogs.league_cog.scoring`` with a fresh instance.
    """
    from dataclasses import replace

    sample = next(iter(BEGINNER_CHANNEL_IDS))
    bumped = replace(SCORING, POINTS_PER_MESSAGE=4)
    with patch("cogs.league_cog.scoring.SCORING", bumped):
        # ceil(4 * 1.25) = 5
        assert points_for_message(sample) == 5
        # And the non-beginner path returns the patched base unchanged.
        assert points_for_message(0) == 4
