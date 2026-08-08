"""Tests for the $myclock activity clock — renderer, helpers, and command.

No Discord connection or database: the renderer is a pure function of the
hour list, the timezone helpers are pure, and the command callback is driven
with a fake context (same approach as test_activity_launch_commands.py).
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Any, cast

import discord
from PIL import Image

from cogs.stats_cog import clock
from cogs.stats_cog.main import StatsCog
from cogs.stats_cog.views import (
    ClockLauncherView,
    _format_offset,
    _now_at_offset,
)


@dataclass
class FakeContext:
    """Minimal command context that records sent messages."""

    sent: list[dict[str, Any]] = field(default_factory=list)

    async def send(self, **kwargs: Any) -> None:
        self.sent.append(kwargs)


# ── Renderer ──

def test_render_returns_square_png() -> None:
    hours = [1, 0, 0, 2, 5, 9] + [0] * 18
    buf = clock.render_activity_clock(hours, utc_offset=1)
    assert isinstance(buf, io.BytesIO)
    img = Image.open(buf)
    assert img.format == "PNG"
    assert img.width == img.height  # square clock face


def test_render_handles_all_zero_hours() -> None:
    # Defensive: renderer must not divide by zero when there is no activity.
    buf = clock.render_activity_clock([0] * 24, utc_offset=0)
    assert Image.open(buf).format == "PNG"


def test_render_rejects_nothing_within_range() -> None:
    # A single dominant hour should still render cleanly (peak normalization).
    hours = [0] * 24
    hours[21] = 500
    buf = clock.render_activity_clock(hours, utc_offset=-5)
    assert Image.open(buf).format == "PNG"


# ── Timezone helpers ──

def test_format_offset_uses_unicode_minus() -> None:
    assert _format_offset(1) == "UTC+1"
    assert _format_offset(0) == "UTC+0"
    assert _format_offset(-5) == "UTC−5"  # U+2212, not ASCII hyphen


def test_now_at_offset_is_hhmm() -> None:
    label = _now_at_offset(3)
    hh, _, mm = label.partition(":")
    assert len(label) == 5 and 0 <= int(hh) <= 23 and 0 <= int(mm) <= 59


# ── Command ──

async def test_myclock_posts_launcher() -> None:
    cog = StatsCog.__new__(StatsCog)
    cog.bot = cast(Any, object())
    ctx = FakeContext()

    callback = cast(Any, cog.myclock.callback)
    await callback(cog, ctx)

    assert len(ctx.sent) == 1
    embed = ctx.sent[0]["embed"]
    view = ctx.sent[0]["view"]
    assert isinstance(embed, discord.Embed)
    assert "reloj de actividad" in (embed.title or "")
    assert isinstance(view, ClockLauncherView)
    button = view.children[0]
    assert isinstance(button, discord.ui.Button)
    assert button.label == "Ver mi reloj"
