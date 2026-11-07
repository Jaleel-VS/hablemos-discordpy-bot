"""Tests for the $myclock activity clock — renderer, helpers, and command.

No Discord connection or database: the renderer is a pure function of the
hour list, the timezone helpers are pure, and the command callback is driven
with a fake context (same approach as test_activity_launch_commands.py).
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Any, TypedDict, cast

import discord
from PIL import Image

from cogs.stats_cog import clock
from cogs.stats_cog.main import StatsCog
from cogs.stats_cog.views import (
    ClockLauncherView,
    ClockResultView,
    _format_offset,
    _now_at_offset,
    _public_clock_view,
)


class SentMessage(TypedDict, total=False):
    """Keyword arguments captured from the fake command context."""

    embed: discord.Embed
    view: discord.ui.View


@dataclass
class FakeContext:
    """Minimal command context that records sent messages."""

    sent: list[SentMessage] = field(default_factory=list)
    author: Any = field(default_factory=lambda: discord.Object(id=42))

    async def send(self, **kwargs: Any) -> None:
        message: SentMessage = {}
        if "embed" in kwargs:
            message["embed"] = kwargs["embed"]
        if "view" in kwargs:
            message["view"] = kwargs["view"]
        self.sent.append(message)


def test_render_returns_square_png() -> None:
    hours = [1, 0, 0, 2, 5, 9] + [0] * 18
    buf = clock.render_activity_clock(hours, utc_offset=1)
    assert isinstance(buf, io.BytesIO)
    img = Image.open(buf)
    assert img.format == "PNG"
    assert img.width == img.height


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


def test_format_offset_uses_unicode_minus() -> None:
    assert _format_offset(1) == "UTC+1"
    assert _format_offset(0) == "UTC+0"
    assert _format_offset(-5) == "UTC−5"  # U+2212, not ASCII hyphen


def test_now_at_offset_is_hhmm() -> None:
    label = _now_at_offset(3)
    hh, _, mm = label.partition(":")
    assert len(label) == 5 and 0 <= int(hh) <= 23 and 0 <= int(mm) <= 59


def _buttons(view: discord.ui.LayoutView) -> list[discord.ui.Button]:
    return [c for c in view.walk_children() if isinstance(c, discord.ui.Button)]


def _text(view: discord.ui.LayoutView) -> str:
    return "\n".join(
        c.content for c in view.walk_children() if isinstance(c, discord.ui.TextDisplay)
    )


def _gallery_urls(view: discord.ui.LayoutView) -> list[str]:
    return [
        item.media.url
        for c in view.walk_children()
        if isinstance(c, discord.ui.MediaGallery)
        for item in c.items
    ]


def test_result_view_has_clock_image_and_both_actions() -> None:
    view = ClockResultView(cast(Any, object()), offset=1)
    labels = [b.label for b in _buttons(view)]
    assert "Publicar en el canal" in labels
    assert "Cambiar zona horaria" in labels
    assert _gallery_urls(view) == ["attachment://activity_clock.png"]
    assert "UTC+1" in _text(view)


@dataclass
class FakeUser:
    display_name: str = "Ada"


def test_public_clock_view_attributes_owner_without_controls() -> None:
    view = _public_clock_view(cast(Any, FakeUser()), offset=-5)
    assert "Ada" in _text(view)
    assert "UTC−5" in _text(view)
    assert _gallery_urls(view) == ["attachment://activity_clock.png"]
    assert _buttons(view) == []


async def test_myclock_posts_launcher() -> None:
    cog = StatsCog.__new__(StatsCog)
    cog.bot = cast(Any, object())
    ctx = FakeContext()

    callback = cast(Any, cog.myclock.callback)
    await callback(cog, ctx)

    assert len(ctx.sent) == 1
    assert "embed" not in ctx.sent[0]
    view = ctx.sent[0].get("view")
    assert isinstance(view, ClockLauncherView)
    assert "reloj de actividad" in _text(view)
    [button] = _buttons(view)
    assert button.label == "Ver mi reloj"
    assert button.custom_id == "stats_clock:launch"
    assert view.is_persistent()
    assert view.owner_id == 42
