"""Pillow renderer for the world clock board: a grid of digital time cards.

Each card is tinted by its local time of day (navy night, coral dawn, sky day,
amber dusk), so a row reads like the sun moving across the world. Drawn at
``S`` times display size and LANCZOS-downsampled to ``OUTPUT_SCALE``, like the
other renderers; every coordinate below is in display units times ``S``.

CPU-bound; call via ``asyncio.to_thread``.
"""
from __future__ import annotations

import functools
import io
import itertools
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .board import Card

SCALE = 3
OUTPUT_SCALE = 2
S = SCALE * OUTPUT_SCALE

_COLUMNS = 4
_CARD_W = 200
_CARD_H = 120
_GAP = 12
_MARGIN = 20
_HEADER_H = 48
_RADIUS = 14
_PAD = 16

_COGS = Path(__file__).resolve().parent.parent
_INTER = _COGS / "utils" / "fonts" / "Inter.ttf"
_NOTO_SC = _COGS / "spotify_cog" / "fonts" / "NotoSansSC.ttf"  # CJK fallback

_PAGE = (17, 19, 26)
_TITLE = (240, 242, 247)
_SUBTITLE = (150, 158, 172)
_YOU_RING = (88, 101, 242)
_SUN = (255, 214, 102)
_MOON = (226, 230, 245)
_DARK_TEXT = (20, 24, 33)
_LIGHT_TEXT = (245, 247, 250)

# (local hour, card colour); interpolated between stops.
_SKY: tuple[tuple[float, tuple[int, int, int]], ...] = (
    (0.0, (22, 27, 58)),
    (4.5, (30, 36, 82)),
    (6.0, (214, 112, 96)),
    (8.0, (110, 170, 225)),
    (16.5, (95, 160, 222)),
    (18.5, (232, 150, 70)),
    (20.0, (70, 52, 110)),
    (22.0, (22, 27, 58)),
    (24.0, (22, 27, 58)),
)


@functools.cache
def _font(path: Path, size: int, weight: str) -> ImageFont.FreeTypeFont:
    """A variable font at display *size*, scaled to the canvas."""
    font = ImageFont.truetype(str(path), size * S)
    font.set_variation_by_name(weight)
    return font


@functools.cache
def _probe(path: Path) -> tuple[ImageFont.FreeTypeFont, tuple[int, int, int, int] | None]:
    """A small copy of the font and the bounding box of its missing-glyph box."""
    font = ImageFont.truetype(str(path), 24)
    return font, font.getmask("\uffff").getbbox()


def _covers(path: Path, text: str) -> bool:
    """True when the font has a real glyph for every visible character."""
    font, missing = _probe(path)
    return all(ch.isspace() or font.getmask(ch).getbbox() != missing for ch in text)


def _font_path_for(text: str) -> Path:
    return _INTER if _covers(_INTER, text) else _NOTO_SC


def can_draw(text: str) -> bool:
    """True when the board can render *text* without missing-glyph boxes."""
    return _covers(_INTER, text) or _covers(_NOTO_SC, text)


def grid_shape(count: int) -> tuple[int, int]:
    """(columns, rows): fewest rows of up to four (three rows at most), cards spread evenly."""
    rows = min(3, math.ceil(max(1, count) / _COLUMNS))
    return math.ceil(max(1, count) / rows), rows


def _sky_colour(hour: float) -> tuple[int, int, int]:
    for (h0, c0), (h1, c1) in itertools.pairwise(_SKY):
        if h0 <= hour <= h1:
            t = (hour - h0) / (h1 - h0)
            return tuple(round(a + (b - a) * t) for a, b in zip(c0, c1, strict=True))  # type: ignore[return-value]
    return _SKY[-1][1]


def _text_colours(bg: tuple[int, int, int]) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """(main, muted) text colours readable on *bg*."""
    luminance = (0.299 * bg[0] + 0.587 * bg[1] + 0.114 * bg[2]) / 255
    main = _DARK_TEXT if luminance > 0.55 else _LIGHT_TEXT
    muted = tuple(round(m * 0.72 + b * 0.28) for m, b in zip(main, bg, strict=True))
    return main, muted  # type: ignore[return-value]


def _fit(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, width: float) -> str:
    """Trim *text* with an ellipsis until it fits *width* canvas pixels."""
    if draw.textlength(text, font=font) <= width:
        return text
    while text and draw.textlength(text + "…", font=font) > width:
        text = text[:-1]
    return text.rstrip() + "…"


def _draw_sky_icon(draw: ImageDraw.ImageDraw, cx: float, cy: float, hour: float, bg: tuple[int, int, int]) -> None:
    r = 9 * S
    if 6.0 <= hour < 18.5:
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=_SUN)
        return
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=_MOON)
    ox, oy = 5 * S, -4 * S
    draw.ellipse([cx - r + ox, cy - r + oy, cx + r + ox, cy + r + oy], fill=bg)


def _footer(card: Card) -> str:
    day = card.local.strftime("%a")
    if card.day_shift:
        day += f" {card.day_shift:+d}"
    return f"{day} · {card.offset}"


def _draw_card(draw: ImageDraw.ImageDraw, card: Card, x: float, y: float) -> None:
    hour = card.local.hour + card.local.minute / 60
    bg = _sky_colour(hour)
    main, muted = _text_colours(bg)
    box = [x, y, x + _CARD_W * S, y + _CARD_H * S]
    outline = _YOU_RING if card.is_you else None
    draw.rounded_rectangle(box, radius=_RADIUS * S, fill=bg, outline=outline, width=3 * S if outline else 0)

    label_font = _font(_font_path_for(card.label), 15, "SemiBold")
    label = _fit(draw, card.label, label_font, (_CARD_W - 2 * _PAD - 28) * S)
    draw.text((x + _PAD * S, y + 14 * S), label, font=label_font, fill=main)
    _draw_sky_icon(draw, x + (_CARD_W - 24) * S, y + 23 * S, hour, bg)

    draw.text((x + _PAD * S, y + 36 * S), card.local.strftime("%H:%M"),
              font=_font(_INTER, 40, "Bold"), fill=main)

    small = _font(_INTER, 12, "Medium")
    footer_y = y + (_CARD_H - 26) * S
    draw.text((x + _PAD * S, footer_y), _footer(card), font=small,
              fill=main if card.day_shift else muted)
    if card.difference is not None:
        right = x + (_CARD_W - _PAD) * S
        draw.text((right - draw.textlength(card.difference, font=small), footer_y),
                  card.difference, font=small, fill=muted)


def render_world_clock(cards: list[Card], title: str, subtitle: str) -> io.BytesIO:
    """Render *cards* west to east under a title row; returns a PNG buffer."""
    columns, rows = grid_shape(len(cards))
    width = 2 * _MARGIN + columns * _CARD_W + (columns - 1) * _GAP
    height = _MARGIN + _HEADER_H + rows * _CARD_H + (rows - 1) * _GAP + _MARGIN
    img = Image.new("RGB", (width * S, height * S), _PAGE)
    draw = ImageDraw.Draw(img)

    draw.text((_MARGIN * S, _MARGIN * S), title,
              font=_font(_font_path_for(title), 20, "Bold"), fill=_TITLE)
    sub_font = _font(_font_path_for(subtitle), 12, "Medium")
    draw.text((_MARGIN * S, (_MARGIN + 26) * S), subtitle, font=sub_font, fill=_SUBTITLE)

    top = (_MARGIN + _HEADER_H) * S
    for i, card in enumerate(cards):
        row, col = divmod(i, columns)
        x = (_MARGIN + col * (_CARD_W + _GAP)) * S
        y = top + row * (_CARD_H + _GAP) * S
        _draw_card(draw, card, x, y)

    img = img.resize((width * OUTPUT_SCALE, height * OUTPUT_SCALE), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf
