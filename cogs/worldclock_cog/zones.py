"""Timezone parsing for the world clock.

A saved clock stores one *zone key*: either an IANA name (``Europe/Berlin``,
handled by ``zoneinfo`` so daylight saving is automatic) or a fixed offset
written ``UTC+05:30``. The two never collide because no IANA name starts with
``UTC+`` or ``UTC-``.
"""
from __future__ import annotations

import functools
import logging
import re
import unicodedata
from datetime import UTC, time, timedelta, timezone, tzinfo
from importlib import resources
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

from .config import ZONE_ALIASES

logger = logging.getLogger(__name__)

_MIN_OFFSET = -12 * 60
_MAX_OFFSET = 14 * 60
_FIXED_KEY = re.compile(r"^UTC([+-])(\d{2}):(\d{2})$")
_OFFSET_INPUT = re.compile(r"^(?:utc|gmt)?\s*([+\-−])\s*(\d{1,2})(?:[:.h]?(\d{2}))?$")
_TIME_INPUT = re.compile(r"^(\d{1,2})(?:[:.h](\d{2}))?\s*(am|pm)?$")


def _normalize(text: str) -> str:
    """Lowercase, strip accents, and treat ``_``/``-`` as spaces."""
    decomposed = unicodedata.normalize("NFKD", text)
    plain = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(plain.lower().replace("_", " ").replace("-", " ").split())


@functools.cache
def canonical_zones() -> frozenset[str]:
    """Canonical IANA zones from tzdata's ``zone.tab``, without legacy links
    such as ``America/Buenos_Aires`` or ``Asia/Calcutta``."""
    text = resources.files("tzdata.zoneinfo").joinpath("zone.tab").read_text(encoding="utf-8")
    return frozenset(
        line.split("\t")[2] for line in text.splitlines() if line and not line.startswith("#")
    )


@functools.cache
def _place_index() -> dict[str, str]:
    """Map normalized place names (``new york``, ``berlin``) to canonical zones."""
    index: dict[str, str] = {}
    for name in sorted(canonical_zones()):
        index.setdefault(_normalize(name.rsplit("/", 1)[-1]), name)
    for name in sorted(canonical_zones()):
        index.setdefault(_normalize(name), name)
    index.update(ZONE_ALIASES)
    return index


@functools.cache
def _any_zone_names() -> dict[str, str]:
    """Every region-qualified IANA name, legacy links included, for exact input."""
    return {_normalize(name): name for name in available_timezones() if "/" in name}


def _fixed_key(minutes: int) -> str:
    sign = "-" if minutes < 0 else "+"
    hours, mins = divmod(abs(minutes), 60)
    return f"UTC{sign}{hours:02d}:{mins:02d}"


def _parse_offset(text: str) -> int | None:
    """Minutes east of UTC for ``UTC+2``, ``gmt-5``, ``+5:30``; None otherwise."""
    if text in ("utc", "gmt", "z"):
        return 0
    match = _OFFSET_INPUT.match(text)
    if match is None:
        return None
    sign, hours, mins = match.group(1), int(match.group(2)), int(match.group(3) or 0)
    if mins not in (0, 15, 30, 45):
        return None
    minutes = hours * 60 + mins
    minutes = minutes if sign == "+" else -minutes
    if not _MIN_OFFSET <= minutes <= _MAX_OFFSET:
        return None
    return minutes


def resolve_zone(text: str) -> str | None:
    """Turn what a member typed into a zone key, or None if unrecognized."""
    cleaned = " ".join(text.strip().lower().split())
    if not cleaned:
        return None
    offset = _parse_offset(cleaned)
    if offset is not None:
        return _fixed_key(offset)
    if _FIXED_KEY.match(text.strip()):
        return text.strip()
    key = _normalize(cleaned)
    return _place_index().get(key) or _any_zone_names().get(key)


def zone_from_key(key: str) -> tzinfo:
    """Load a stored zone key. Raises ``ValueError`` for an unknown key."""
    match = _FIXED_KEY.match(key)
    if match is not None:
        minutes = int(match.group(2)) * 60 + int(match.group(3))
        return timezone(timedelta(minutes=minutes if match.group(1) == "+" else -minutes))
    try:
        return ZoneInfo(key)
    except (ZoneInfoNotFoundError, ValueError) as e:
        raise ValueError(f"unknown zone key {key!r}") from e


def is_fixed(key: str) -> bool:
    """True when the key is a fixed offset, which ignores daylight saving."""
    return _FIXED_KEY.match(key) is not None


def format_offset(delta: timedelta) -> str:
    """``UTC+1``, ``UTC+5:30``, ``UTC−3`` (Unicode minus)."""
    minutes = int(delta.total_seconds() // 60)
    sign = "−" if minutes < 0 else "+"
    hours, mins = divmod(abs(minutes), 60)
    return f"UTC{sign}{hours}" + (f":{mins:02d}" if mins else "")


def format_difference(delta: timedelta) -> str:
    """Offset of a clock from the viewer: ``+1h``, ``−5:30``, ``same``."""
    minutes = int(delta.total_seconds() // 60)
    if minutes == 0:
        return "same"
    sign = "−" if minutes < 0 else "+"
    hours, mins = divmod(abs(minutes), 60)
    return f"{sign}{hours}:{mins:02d}" if mins else f"{sign}{hours}h"


def suggest_zones(current: str, limit: int = 25) -> list[tuple[str, str]]:
    """Autocomplete: ``(display, zone key)`` pairs matching *current*."""
    query = _normalize(current)
    offset = _parse_offset(" ".join(current.strip().lower().split()))
    if offset is not None:
        key = _fixed_key(offset)
        return [(f"{key} (fixed, no daylight saving)", key)]

    seen: set[str] = set()
    starts: list[tuple[str, str]] = []
    contains: list[tuple[str, str]] = []
    for place, key in _place_index().items():
        if key in seen or (query and query not in place):
            continue
        seen.add(key)
        bucket = starts if place.startswith(query) else contains
        bucket.append((f"{place.title()} — {key}", key))
    return (starts + contains)[:limit]


def parse_clock_time(text: str) -> time | None:
    """Parse ``20:00``, ``20``, ``8pm``, ``8:30 am``; None when invalid."""
    match = _TIME_INPUT.match(text.strip().lower())
    if match is None:
        return None
    hour, minute, meridiem = int(match.group(1)), int(match.group(2) or 0), match.group(3)
    if meridiem is not None:
        if not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if meridiem == "pm" else 0)
    if hour > 23 or minute > 59:
        return None
    return time(hour, minute)


def home_zone(utc_offset: int | None) -> tzinfo | None:
    """The viewer's zone from their ``$myclock`` whole-hour offset."""
    if utc_offset is None:
        return None
    return UTC if utc_offset == 0 else timezone(timedelta(hours=utc_offset))
