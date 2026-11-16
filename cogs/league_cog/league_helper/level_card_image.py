"""Level cards for the Language League: the level-up card and ``/league level``.

Draws a frosted panel with the numbers on the tier's background image (see
``cogs/league_cog/levels.py`` and ``scripts/generate_level_backgrounds.py``),
plus the member's avatar. Rendered at ``S`` times display size and
LANCZOS-downsampled to ``OUTPUT_SCALE``; coordinates below are display units
multiplied by ``S``. CPU- and network-bound (avatar fetch); call via
``asyncio.to_thread``.
"""
from __future__ import annotations

import functools
import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageStat

from cogs.league_cog.levels import LevelProgress, tier_for_level

from .leaderboard_image_pillow import create_default_avatar, download_avatar

SCALE = 3
OUTPUT_SCALE = 2
S = SCALE * OUTPUT_SCALE

_W = 900
_H = 240
#: Size the committed backgrounds are stored at: the output resolution.
BACKGROUND_SIZE = (_W * OUTPUT_SCALE, _H * OUTPUT_SCALE)

_PANEL = (20, 20, 670, 220)
_PANEL_RADIUS = 24
_AVATAR_CENTER = (785, 120)
_AVATAR_RADIUS = 75
_AVATAR_RING = 5
_TEXT_X = 55

_SORA = Path(__file__).resolve().parents[2] / "utils" / "fonts" / "Sora.ttf"

_DARK = (34, 30, 48)
_LIGHT = (255, 255, 255)
#: Mean panel luminance above which the text turns dark.
_LIGHT_BACKGROUND = 150


@functools.cache
def _font(size: int, weight: str) -> ImageFont.FreeTypeFont:
    font = ImageFont.truetype(str(_SORA), size * S)
    font.set_variation_by_name(weight)
    return font


@functools.cache
def _background(path: Path) -> Image.Image:
    return Image.open(path).convert("RGB")


def _scaled(box: tuple[int, int, int, int], k: int) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = box
    return x0 * k, y0 * k, x1 * k, y1 * k


def _base(level: int) -> tuple[Image.Image, tuple[int, int, int]]:
    """The tier background with the frosted panel, and the text colour to use on it."""
    bg = _background(tier_for_level(level).background).copy()
    box = _scaled(_PANEL, OUTPUT_SCALE)
    panel = bg.crop(box)
    light = ImageStat.Stat(panel.convert("L")).mean[0] > _LIGHT_BACKGROUND
    # Blur at stored size: the result is smooth, so upscaling it loses nothing.
    blurred = panel.filter(ImageFilter.GaussianBlur(15 * OUTPUT_SCALE))
    mask = Image.new("L", blurred.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, *blurred.size), _PANEL_RADIUS * OUTPUT_SCALE, fill=255,
    )
    bg.paste(blurred, (box[0], box[1]), mask)

    canvas = bg.resize((_W * S, _H * S), Image.Resampling.BICUBIC)
    _draw(canvas).rounded_rectangle(
        _scaled(_PANEL, S),
        _PANEL_RADIUS * S,
        fill=(255, 255, 255, 70) if light else (20, 16, 40, 70),
        outline=(255, 255, 255, 110),
        width=S,
    )
    return canvas, _DARK if light else _LIGHT


def _draw(canvas: Image.Image) -> ImageDraw.ImageDraw:
    """A drawer that alpha-blends translucent fills onto the RGB canvas."""
    return ImageDraw.Draw(canvas, "RGBA")


def _draw_avatar(canvas: Image.Image, avatar_url: str | None) -> None:
    size = _AVATAR_RADIUS * 2 * S
    avatar = download_avatar(avatar_url, size) if avatar_url else create_default_avatar(size)
    cx, cy = (v * S for v in _AVATAR_CENTER)
    ring = (_AVATAR_RADIUS + _AVATAR_RING) * S
    _draw(canvas).ellipse(
        (cx - ring, cy - ring, cx + ring, cy + ring), fill=(255, 255, 255, 210),
    )
    circle = Image.new("L", (size, size), 0)
    ImageDraw.Draw(circle).ellipse((0, 0, size, size), fill=255)
    canvas.paste(avatar.convert("RGB"), (cx - size // 2, cy - size // 2), circle)


def _export(canvas: Image.Image) -> io.BytesIO:
    out = canvas.resize(BACKGROUND_SIZE, Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    out.save(buf, "PNG", optimize=True)
    buf.seek(0)
    return buf


def _muted(colour: tuple[int, int, int]) -> tuple[int, int, int, int]:
    return (*colour, 180)


def render_level_up(old_level: int, progress: LevelProgress, avatar_url: str | None) -> io.BytesIO:
    """The card posted when a member goes from ``old_level`` to ``progress.level``."""
    canvas, fg = _base(progress.level)
    draw = _draw(canvas)
    draw.text((_TEXT_X * S, 38 * S), "LEVEL UP", font=_font(23, "SemiBold"), fill=_muted(fg))

    numbers = _font(75, "ExtraBold")
    x, y = _TEXT_X * S - 3 * S, 66 * S
    draw.text((x, y), str(old_level), font=numbers, fill=_muted(fg))
    x += round(draw.textlength(str(old_level), font=numbers)) + 26 * S
    arrow_y = y + 48 * S
    draw.line((x, arrow_y, x + 56 * S, arrow_y), fill=fg, width=7 * S)
    draw.polygon(
        [(x + 76 * S, arrow_y), (x + 50 * S, arrow_y - 18 * S), (x + 50 * S, arrow_y + 18 * S)],
        fill=fg,
    )
    x += 102 * S
    draw.text((x, y), str(progress.level), font=numbers, fill=fg)

    subtitle = (
        f"{tier_for_level(progress.level).name}  ·  "
        f"{progress.to_next:,} pts to level {progress.level + 1}"
    )
    draw.text((_TEXT_X * S + 2 * S, 176 * S), subtitle, font=_font(20, "Regular"), fill=_muted(fg))
    _draw_avatar(canvas, avatar_url)
    return _export(canvas)


def render_level_card(progress: LevelProgress, avatar_url: str | None) -> io.BytesIO:
    """A member's current level and progress toward the next one."""
    canvas, fg = _base(progress.level)
    draw = _draw(canvas)
    tier = tier_for_level(progress.level).name.upper()
    draw.text((_TEXT_X * S, 38 * S), tier, font=_font(23, "SemiBold"), fill=_muted(fg))
    draw.text(
        (_TEXT_X * S - 3 * S, 66 * S), f"Level {progress.level}",
        font=_font(64, "ExtraBold"), fill=fg,
    )

    x0, x1 = _TEXT_X * S, 635 * S
    y0, y1 = 150 * S, 164 * S
    radius = (y1 - y0) // 2
    draw.rounded_rectangle((x0, y0, x1, y1), radius, fill=(*fg, 60))
    filled = x0 + round((x1 - x0) * progress.fraction)
    if filled - x0 >= 2 * radius:
        draw.rounded_rectangle((x0, y0, filled, y1), radius, fill=fg)

    subtitle = (
        f"{progress.xp:,} XP  ·  {progress.to_next:,} pts to level {progress.level + 1}"
    )
    draw.text((_TEXT_X * S + 2 * S, 176 * S), subtitle, font=_font(20, "Regular"), fill=_muted(fg))
    _draw_avatar(canvas, avatar_url)
    return _export(canvas)
