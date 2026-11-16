"""The level curve stays staggered, consistent and on the agreed pace."""
from itertools import pairwise

import pytest

from cogs.league_cog.levels import (
    TIERS,
    XpGain,
    level_for_xp,
    progress_for_xp,
    tier_for_level,
    xp_for_level,
)


@pytest.mark.parametrize("level", range(2, 201))
def test_level_starts_exactly_at_its_threshold(level: int) -> None:
    threshold = xp_for_level(level)
    assert level_for_xp(threshold) == level
    assert level_for_xp(threshold - 1) == level - 1


def test_later_levels_cost_more() -> None:
    costs = [xp_for_level(level + 1) - xp_for_level(level) for level in range(1, 200)]
    # Rounding can make neighbouring levels cost the same, never less.
    assert all(b >= a for a, b in pairwise(costs))
    blocks = [xp_for_level(level + 10) - xp_for_level(level) for level in range(1, 200, 10)]
    assert all(b > a for a, b in pairwise(blocks))


def test_pace_for_a_learner_earning_50_points_a_day() -> None:
    assert 12 <= xp_for_level(10) / 50 <= 16
    assert 150 <= xp_for_level(50) / 50 <= 200


def test_progress_reports_points_to_next_level() -> None:
    progress = progress_for_xp(xp_for_level(5) + 3)
    assert progress.level == 5
    assert progress.to_next == xp_for_level(6) - xp_for_level(5) - 3
    assert 0 < progress.fraction < 1


def test_gain_detects_crossing_a_threshold() -> None:
    threshold = xp_for_level(3)
    assert XpGain(threshold - 1, threshold, True).leveled_up
    assert not XpGain(threshold, threshold + 1, True).leveled_up


def test_tiers_switch_at_their_first_level_and_have_backgrounds() -> None:
    for previous, tier in pairwise(TIERS):
        assert tier_for_level(tier.min_level) == tier
        assert tier_for_level(tier.min_level - 1) == previous
    for tier in TIERS:
        assert tier.background.is_file()
