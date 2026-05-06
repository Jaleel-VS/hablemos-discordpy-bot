"""Shared embed helper functions."""
from __future__ import annotations

from discord import Color, Embed

ERROR_COLOR = 0xE74C3C
SUCCESS_COLOR = 0x57F287
INFO_COLOR = 0x3498DB
WARNING_COLOR = 0xF1C40F

EMBED_COLORS = [
    SUCCESS_COLOR,
    ERROR_COLOR,
    0xEB459E,
    WARNING_COLOR,
    0xF47FFF,
    0x7289DA,
    0xE67E22,
    0x9B59B6,
    INFO_COLOR,
    0x2ECC71,
    0x1ABC9C,
]


def make_embed(
    text: str,
    *,
    title: str | None = None,
    color: int | Color = INFO_COLOR,
) -> Embed:
    """Create a standard bot embed."""
    return Embed(title=title, description=text, color=color)


def green_embed(text: str, *, title: str | None = None) -> Embed:
    """Create a success/answer embed."""
    return make_embed(text, title=title, color=SUCCESS_COLOR)


def red_embed(text: str, *, title: str | None = None) -> Embed:
    """Create an error embed."""
    return make_embed(text, title=title, color=ERROR_COLOR)


def blue_embed(text: str, *, title: str | None = None) -> Embed:
    """Create an information embed."""
    return make_embed(text, title=title, color=INFO_COLOR)


def yellow_embed(text: str, *, title: str | None = None) -> Embed:
    """Create a warning embed."""
    return make_embed(text, title=title, color=WARNING_COLOR)
