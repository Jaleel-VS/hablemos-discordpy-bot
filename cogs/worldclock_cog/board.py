"""Board model: which clocks to draw and what each card says.

Pure functions of an instant, so tests pin the time and the renderer only
draws what it is handed.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta, tzinfo

from db.world_clock import SavedClock

from .config import DEFAULT_CLOCKS
from .zones import format_difference, format_offset, zone_from_key

logger = logging.getLogger(__name__)

YOU_LABEL = "You"


@dataclass(frozen=True)
class Clock:
    """A labelled zone ready to read."""

    label: str
    zone: tzinfo


@dataclass(frozen=True)
class Card:
    """Everything one card shows."""

    label: str
    local: datetime
    day_shift: int        # local date minus the viewer's date: -1, 0, +1
    offset: str           # "UTC+1"
    difference: str | None  # "+1h" from the viewer; None without a home zone
    is_you: bool


def saved_clocks(saved: list[SavedClock]) -> list[Clock]:
    """Load saved rows, dropping any whose zone no longer exists."""
    clocks: list[Clock] = []
    for row in saved:
        try:
            clocks.append(Clock(row.label, zone_from_key(row.zone)))
        except ValueError:
            logger.warning("Skipping world clock with unknown zone %s", row.zone)
    return clocks


def default_clocks() -> list[Clock]:
    """The board shown before a member saves any clocks."""
    return [Clock(label, zone_from_key(key)) for label, key in DEFAULT_CLOCKS]


def _offset_of(moment: datetime) -> timedelta:
    """UTC offset of an aware datetime; every zone we load defines one."""
    return moment.utcoffset() or timedelta(0)


def build_cards(clocks: list[Clock], instant: datetime, home: tzinfo | None) -> list[Card]:
    """Cards ordered west to east, with a "You" card when *home* is known."""
    home_now = instant.astimezone(home or UTC)
    home_offset = _offset_of(home_now)

    entries = [(c.label, c.zone, False) for c in clocks]
    if home is not None:
        entries.append((YOU_LABEL, home, True))

    cards: list[tuple[timedelta, Card]] = []
    for label, zone, is_you in entries:
        local = instant.astimezone(zone)
        offset = _offset_of(local)
        show_difference = home is not None and not is_you
        cards.append((offset, Card(
            label=label,
            local=local,
            day_shift=(local.date() - home_now.date()).days,
            offset=format_offset(offset),
            difference=format_difference(offset - home_offset) if show_difference else None,
            is_you=is_you,
        )))
    cards.sort(key=lambda pair: (pair[0], not pair[1].is_you))
    return [card for _, card in cards]


def planned_instant(at: time, home: tzinfo | None, now: datetime) -> datetime:
    """Today's *at* in the viewer's zone (UTC without one)."""
    reference = home or UTC
    return datetime.combine(now.astimezone(reference).date(), at, tzinfo=reference)
