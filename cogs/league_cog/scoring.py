"""Points-per-message calculations for the Language League.

Kept as a standalone module (rather than inline in ``main.py``) so the
logic is trivially unit-testable without spinning up the whole cog.
"""
from __future__ import annotations

import math

from cogs.league_cog.config import (
    BEGINNER_CHANNEL_IDS,
    BEGINNER_CHANNEL_MULTIPLIER,
    SCORING,
)


def get_channel_multiplier(channel_id: int) -> float:
    """Return the point multiplier for ``channel_id``.

    Defaults to ``1.0``. Beginner channels return
    :data:`BEGINNER_CHANNEL_MULTIPLIER` to reward learners who are still
    in the early channels, where message volume tends to be lower.
    """
    if channel_id in BEGINNER_CHANNEL_IDS:
        return BEGINNER_CHANNEL_MULTIPLIER
    return 1.0


def points_for_message(channel_id: int) -> int:
    """Return the integer points a single counted message is worth.

    Applies any per-channel multiplier on top of
    ``SCORING.POINTS_PER_MESSAGE`` and rounds up so sub-integer awards
    still translate into an actual bonus (e.g. 1 × 1.25 → 2, not 1).
    """
    base = SCORING.POINTS_PER_MESSAGE
    multiplier = get_channel_multiplier(channel_id)
    if multiplier == 1.0:
        return base
    return math.ceil(base * multiplier)
