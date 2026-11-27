"""League cards: the level-up card and the ``/league profile`` card.

Both draw a frosted panel on the tier's background image (see
``cogs/league_cog/levels.py`` and ``scripts/generate_level_backgrounds.py``),
plus the member's avatar, in the language from ``card_text.py``. The frosted
background is built once per tier and card size, then rendered at ``S`` times
display size and LANCZOS-downsampled to ``OUTPUT_SCALE``; coordinates below are
display units multiplied by ``S``. CPU- and network-bound (avatar fetch); call
via ``asyncio.to_thread``.
"""
from __future__ import annotations

import functools
import io
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageStat

from cogs.league_cog.card_text import CardText
from cogs.league_cog.levels import LevelProgress, tier_for_level
from cogs.league_cog.profile import LeagueProfile, RoundStanding

from .leaderboard_image_pillow import create_default_avatar, download_avatar

SCALE = 2
OUTPUT_SCALE = 2
S = SCALE * OUTPUT_SCALE

_W = 900
_LEVEL_UP_H = 240
_PROFILE_H = 500
#: Size the committed backgrounds are stored at: the level-up card's output size.
BACKGROUND_SIZE = (_W * OUTPUT_SCALE, _LEVEL_UP_H * OUTPUT_SCALE)

_RADIUS = 24
_TEXT_X = 55

_SORA = Path(__file__).resolve().parents[2] / "utils" / "fonts" / "Sora.ttf"

_DARK = (34, 30, 48)
_LIGHT = (255, 255, 255)
#: Mean panel luminance above which the text turns dark.
_LIGHT_BACKGROUND = 150
_UP = (46, 204, 113)
_DOWN = (231, 76, 60)
_MEDALS = ((255, 200, 40), (200, 205, 215), (214, 140, 80))

Box = tuple[int, int, int, int]


@functools.cache
def _font(size: int, weight: str) -> ImageFont.FreeTypeFont:
    font = ImageFont.truetype(str(_SORA), size * S)
    font.set_variation_by_name(weight)
    return font


def _scaled(box: Box, k: int) -> Box:
    x0, y0, x1, y1 = box
    return x0 * k, y0 * k, x1 * k, y1 * k


def _cover(image: Image.Image, width: int, height: int) -> Image.Image:
    """Scale ``image`` to fill ``width`` × ``height``, cropping the overflow evenly."""
    scale = max(width / image.width, height / image.height)
    resized = image.resize(
        (round(image.width * scale), round(image.height * scale)), Image.Resampling.LANCZOS,
    )
    left = (resized.width - width) // 2
    top = (resized.height - height) // 2
    return resized.crop((left, top, left + width, top + height))


def _draw(canvas: Image.Image) -> ImageDraw.ImageDraw:
    """A drawer that alpha-blends translucent fills onto the RGB canvas."""
    return ImageDraw.Draw(canvas, "RGBA")


@functools.cache
def _frosted(path: Path, height: int, panel: Box) -> tuple[Image.Image, bool]:
    """The tier background at output size with the panel blurred, and whether the panel is light.

    Cached per tier and card size; callers must not modify the returned image.
    """
    with Image.open(path) as image:
        bg = _cover(image.convert("RGB"), _W * OUTPUT_SCALE, height * OUTPUT_SCALE)
    box = _scaled(panel, OUTPUT_SCALE)
    region = bg.crop(box)
    light = ImageStat.Stat(region.convert("L")).mean[0] > _LIGHT_BACKGROUND
    # Blur at stored size: the result is smooth, so upscaling it loses nothing.
    blurred = region.filter(ImageFilter.GaussianBlur(15 * OUTPUT_SCALE))
    mask = Image.new("L", blurred.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, *blurred.size), _RADIUS * OUTPUT_SCALE, fill=255,
    )
    bg.paste(blurred, (box[0], box[1]), mask)
    return bg, light


class _Card:
    """A canvas with the tier background, frosted panel and chosen text colour."""

    def __init__(self, level: int, height: int, panel: Box):
        self.height = height
        bg, light = _frosted(tier_for_level(level).background, height, panel)
        # resize returns a new image, so the cached background stays untouched.
        self.canvas = bg.resize((_W * S, height * S), Image.Resampling.BICUBIC)
        self.draw = _draw(self.canvas)
        self.draw.rounded_rectangle(
            _scaled(panel, S),
            _RADIUS * S,
            fill=(255, 255, 255, 70) if light else (20, 16, 40, 70),
            outline=(255, 255, 255, 110),
            width=S,
        )
        self.fg = _DARK if light else _LIGHT
        self.muted = (*self.fg, 180)

    def text(self, x: int, y: int, text: str, size: int, weight: str = "Regular", *,
             muted: bool = False) -> int:
        """Draw at display coordinates; returns the display width drawn."""
        font = _font(size, weight)
        self.draw.text((x * S, y * S), text, font=font, fill=self.muted if muted else self.fg)
        return round(self.draw.textlength(text, font=font) / S)

    def bar(self, box: Box, fraction: float) -> None:
        x0, y0, x1, y1 = _scaled(box, S)
        radius = (y1 - y0) // 2
        self.draw.rounded_rectangle((x0, y0, x1, y1), radius, fill=(*self.fg, 60))
        filled = x0 + round((x1 - x0) * fraction)
        if filled - x0 >= 2 * radius:
            self.draw.rounded_rectangle((x0, y0, filled, y1), radius, fill=self.fg)

    def divider(self, y: int, x0: int, x1: int) -> None:
        self.draw.line((x0 * S, y * S, x1 * S, y * S), fill=(*self.fg, 70), width=S)

    def avatar(self, center: tuple[int, int], radius: int, avatar_url: str | None) -> float:
        """Draw the avatar and return seconds spent loading it, excluding compositing."""
        size = radius * 2 * S
        started = time.perf_counter()
        avatar = download_avatar(avatar_url, size) if avatar_url else create_default_avatar(size)
        load_seconds = time.perf_counter() - started
        cx, cy = center[0] * S, center[1] * S
        ring = (radius + 5) * S
        self.draw.ellipse((cx - ring, cy - ring, cx + ring, cy + ring), fill=(255, 255, 255, 210))
        circle = Image.new("L", (size, size), 0)
        ImageDraw.Draw(circle).ellipse((0, 0, size, size), fill=255)
        self.canvas.paste(avatar.convert("RGB"), (cx - size // 2, cy - size // 2), circle)
        return load_seconds

    def export(self) -> io.BytesIO:
        out = self.canvas.resize(
            (_W * OUTPUT_SCALE, self.height * OUTPUT_SCALE), Image.Resampling.LANCZOS,
        )
        buf = io.BytesIO()
        out.save(buf, "PNG")
        buf.seek(0)
        return buf


def _arrow(card: _Card, x: int, y: int) -> None:
    """A right arrow 76 display px wide, centred vertically on ``y``."""
    d, fg = card.draw, card.fg
    d.line((x * S, y * S, (x + 56) * S, y * S), fill=fg, width=7 * S)
    d.polygon([((x + 76) * S, y * S), ((x + 50) * S, (y - 18) * S), ((x + 50) * S, (y + 18) * S)],
              fill=fg)


def _triangle(card: _Card, x: int, y: int, up: bool, colour: tuple[int, int, int]) -> None:
    """A 12 px movement triangle with its top-left at (x, y)."""
    points = ([(x, y + 12), (x + 14, y + 12), (x + 7, y)] if up
              else [(x, y), (x + 14, y), (x + 7, y + 12)])
    card.draw.polygon([(px * S, py * S) for px, py in points], fill=colour)


def render_level_up(
    old_level: int, progress: LevelProgress, avatar_url: str | None, text: CardText,
) -> io.BytesIO:
    """The card posted when a member goes from ``old_level`` to ``progress.level``."""
    card = _Card(progress.level, _LEVEL_UP_H, (20, 20, 670, 220))
    card.text(_TEXT_X, 38, text.level_up, 23, "SemiBold", muted=True)
    x = _TEXT_X - 3
    x += card.text(x, 66, str(old_level), 75, "ExtraBold", muted=True) + 26
    _arrow(card, x, 114)
    card.text(x + 102, 66, str(progress.level), 75, "ExtraBold")
    tier = text.tier(tier_for_level(progress.level).name)
    to_next = text.to_next.format(points=progress.to_next, level=progress.level + 1)
    card.text(_TEXT_X + 2, 176, f"{tier}  ·  {to_next}", 20, muted=True)
    card.avatar((785, 120), 75, avatar_url)
    return card.export()


def _round_band(card: _Card, standing: RoundStanding, text: CardText) -> None:
    board = text.board_spanish if standing.board == "spanish" else text.board_english
    columns = [
        (f"#{standing.rank}", board),
        (f"#{standing.combined_rank}", text.combined),
        (f"{standing.score:,}", text.score),
        (str(standing.active_days), text.active_days),
    ]
    for i, (value, label) in enumerate(columns):
        x = _TEXT_X + i * 200
        width = card.text(x, 248, value, 34, "Bold")
        card.text(x, 294, label, 18, muted=True)
        if i == 0 and standing.movement:
            up = standing.movement > 0
            _triangle(card, x + width + 10, 262, up, _UP if up else _DOWN)
            card.text(x + width + 28, 255, str(abs(standing.movement)), 20, "SemiBold")

    if standing.above_gap is None:
        rival = (text.alone if standing.below_gap is None
                 else text.leading.format(points=standing.below_gap))
    elif standing.above_gap == 0:
        rival = text.tied.format(rank=standing.rank - 1)
    else:
        rival = text.behind.format(points=standing.above_gap, rank=standing.rank - 1)
    bonus = text.bonus.format(points=standing.points, bonus=standing.bonus)
    card.text(_TEXT_X, 328, f"{rival}  ·  {bonus}", 19, muted=True)


def _history_band(card: _Card, profile: LeagueProfile, text: CardText) -> None:
    card.text(_TEXT_X, 382, text.streak_line(profile.streak, profile.best_streak), 20, "SemiBold")

    x = _TEXT_X
    for colour, count in zip(_MEDALS, profile.podiums, strict=True):
        card.draw.ellipse(_scaled((x, 432, x + 18, 450), S), fill=colour)
        x += 24 + card.text(x + 24, 427, f"×{count}", 19, "SemiBold") + 16
    x += 10
    x += card.text(x, 427, f"{text.champion} ×{profile.champion_weeks}", 19, "SemiBold") + 26
    best_round = f"{profile.best_round:,}" if profile.best_round else "—"
    card.text(x, 427, f"{text.best_round} {best_round}", 19, "SemiBold")

    # Sparkline of the last 7 days' points.
    card.text(650, 380, text.last_7_days, 15, "SemiBold", muted=True)
    peak = max(profile.daily_points) or 1
    for i, points in enumerate(profile.daily_points):
        x0 = 650 + i * 28
        height = max(3, round(44 * points / peak))
        card.draw.rounded_rectangle(
            _scaled((x0, 456 - height, x0 + 19, 456), S), 3 * S,
            fill=card.fg if points else (*card.fg, 70),
        )


def render_profile(
    profile: LeagueProfile, avatar_url: str | None, text: CardText, ends_in: str,
) -> tuple[io.BytesIO, float, float]:
    """Return the profile PNG, avatar load seconds and exclusive render seconds."""
    started = time.perf_counter()
    progress = profile.progress
    card = _Card(progress.level, _PROFILE_H, (20, 20, 880, 480))

    card.text(_TEXT_X, 38, text.tier(tier_for_level(progress.level).name).upper(), 23,
              "SemiBold", muted=True)
    card.text(_TEXT_X - 3, 64, text.level.format(level=progress.level), 60, "ExtraBold")
    card.bar((_TEXT_X, 150, 680, 162), progress.fraction)
    to_next = text.to_next.format(points=progress.to_next, level=progress.level + 1)
    card.text(_TEXT_X + 2, 172, f"{progress.xp:,} XP  ·  {to_next}", 19, muted=True)
    avatar_seconds = card.avatar((785, 112), 68, avatar_url)

    card.divider(212, _TEXT_X, 845)
    header = f"{text.this_round}  ·  {ends_in}" if ends_in else text.this_round
    card.text(_TEXT_X, 222, header, 17, "SemiBold", muted=True)
    if profile.standing:
        _round_band(card, profile.standing, text)
    else:
        card.text(_TEXT_X, 272, text.not_in_league, 21, "SemiBold")

    card.divider(366, _TEXT_X, 845)
    _history_band(card, profile, text)
    buf = card.export()
    return buf, avatar_seconds, time.perf_counter() - started - avatar_seconds
