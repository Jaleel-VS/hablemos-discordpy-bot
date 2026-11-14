"""World clock actions shared by the commands and the manage panel."""
from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import TYPE_CHECKING

import discord

from db.world_clock import SaveClockResult

from . import board, renderer, zones
from .config import MAX_CLOCKS, MAX_LABEL_LEN

if TYPE_CHECKING:
    from db import Database

IMAGE_NAME = "world_clock.png"

_ZONE_HELP = "Try a city (`Berlin`, `Bogotá`), an IANA name (`Europe/Madrid`) or an offset (`UTC+2`)."


@dataclass(frozen=True)
class Outcome:
    """Result of a change, with the reply to show the member."""

    ok: bool
    message: str


@dataclass(frozen=True)
class RenderedBoard:
    """The board image and the text that goes above it."""

    image: io.BytesIO
    title: str
    body: str

    def file(self) -> discord.File:
        return discord.File(self.image, filename=IMAGE_NAME)


def clean_label(text: str) -> str | None:
    """A drawable label of 1-16 characters, or None when it can't be used."""
    label = " ".join(text.split())
    if not 1 <= len(label) <= MAX_LABEL_LEN:
        return None
    if label.lower() == board.YOU_LABEL.lower() or not renderer.can_draw(label):
        return None
    return label


def describe_zone(key: str) -> str:
    """How a saved zone reads in lists and replies."""
    return f"{key} (fixed, no daylight saving)" if zones.is_fixed(key) else key


_LABEL_HELP = (
    f"Names need 1-{MAX_LABEL_LEN} characters, can't be `You`, "
    "and can't contain emoji."
)


def _validate(raw_label: str, raw_zone: str) -> tuple[str, str] | Outcome:
    label = clean_label(raw_label)
    if label is None:
        return Outcome(False, _LABEL_HELP)
    zone = zones.resolve_zone(raw_zone)
    if zone is None:
        return Outcome(False, f"I don't know the timezone `{discord.utils.escape_markdown(raw_zone)}`. {_ZONE_HELP}")
    return label, zone


async def add_clock(db: Database, user_id: int, raw_label: str, raw_zone: str) -> Outcome:
    """Validate and save a clock, replacing the zone of one with the same name."""
    checked = _validate(raw_label, raw_zone)
    if isinstance(checked, Outcome):
        return checked
    label, zone = checked
    result = await db.add_world_clock(user_id, label, zone, MAX_CLOCKS)
    shown = discord.utils.escape_markdown(label)
    match result:
        case SaveClockResult.ADDED:
            return Outcome(True, f"Added **{shown}**: {describe_zone(zone)}.")
        case SaveClockResult.REPLACED:
            return Outcome(True, f"Updated **{shown}**: {describe_zone(zone)}.")
        case _:
            return Outcome(False, f"You already have {MAX_CLOCKS} clocks. Remove one first.")


async def edit_clock(
    db: Database, user_id: int, old_label: str, raw_label: str, raw_zone: str
) -> Outcome:
    """Rename and re-zone an existing clock."""
    checked = _validate(raw_label, raw_zone)
    if isinstance(checked, Outcome):
        return checked
    label, zone = checked
    result = await db.edit_world_clock(user_id, old_label, label, zone)
    shown = discord.utils.escape_markdown(label)
    match result:
        case SaveClockResult.REPLACED:
            return Outcome(True, f"Updated **{shown}**: {describe_zone(zone)}.")
        case SaveClockResult.NAME_TAKEN:
            return Outcome(False, f"You already have a clock called **{shown}**.")
        case _:
            return Outcome(False, "That clock no longer exists.")


async def render_board(
    db: Database, user_id: int, at: time | None, now: datetime | None = None
) -> RenderedBoard:
    """Build and draw a member's board, at *now* or at *at* in their own time."""
    now = now or datetime.now(UTC)
    saved = board.saved_clocks(await db.get_world_clocks(user_id))
    home = zones.home_zone(await db.get_user_clock_tz(user_id))
    clocks = saved or board.default_clocks()

    instant = now if at is None else board.planned_instant(at, home, now)
    cards = board.build_cards(clocks, instant, home)

    title = "Your clocks" if saved else "World clock"
    lines: list[str] = []
    if at is None:
        subtitle = now.strftime("%a %d %b · %H:%M UTC")
    else:
        offset = instant.utcoffset() or timedelta(0)
        where = f"your time ({zones.format_offset(offset)})" if home is not None else "UTC"
        subtitle = f"At {at.strftime('%H:%M')} {where}"
        lines.append(f"At **{at.strftime('%H:%M')}** {where}, which is "
                     f"<t:{int(instant.timestamp())}:F> in your local time.")
    if not saved:
        lines.append(f"These are the default cities. Add your own with `$clock add Emily Berlin` (up to {MAX_CLOCKS}).")
    if home is None:
        lines.append("Pick your timezone with `$myclock` to get a **You** card.")

    image = await asyncio.to_thread(renderer.render_world_clock, cards, title, subtitle)
    return RenderedBoard(image, f"🌍 {title}", "\n".join(lines))
