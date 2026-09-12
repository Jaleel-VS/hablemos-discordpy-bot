"""Apple-inspired dark comparison-card renderer for PPP results."""
from __future__ import annotations

import contextlib
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from cogs.ppp_cog.calculator import display_amount
from cogs.ppp_cog.models import Country, PPPResult

SCALE = 3
OUTPUT_SCALE = 2
S = SCALE * OUTPUT_SCALE
DISPLAY_WIDTH = 800
DISPLAY_HEIGHT = 550
WIDTH = DISPLAY_WIDTH * S
HEIGHT = DISPLAY_HEIGHT * S

ROOT = Path(__file__).resolve().parents[2]
FONT_PATH = ROOT / "cogs" / "vocabcatch_cog" / "fonts" / "Inter.ttf"

BG = "#070709"
SURFACE = "#141417"
SURFACE_2 = "#1C1C20"
BORDER = "#2A2A2F"
WHITE = "#F5F5F7"
SECONDARY = "#A1A1AA"
TERTIARY = "#686871"
GREEN = "#30D158"


def _font(size: int, weight: str = "Regular") -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if FONT_PATH.exists():
        font = ImageFont.truetype(str(FONT_PATH), size * S)
        with contextlib.suppress(OSError, ValueError):
            font.set_variation_by_name(weight)
        return font
    return ImageFont.load_default()


def _text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    value: str,
    size: int,
    fill: str = WHITE,
    weight: str = "Regular",
    anchor: str = "la",
) -> None:
    draw.text((xy[0] * S, xy[1] * S), value, font=_font(size, weight), fill=fill, anchor=anchor)


def _rounded(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    radius: int,
    fill: str,
    outline: str | None = None,
    width: int = 1,
) -> None:
    draw.rounded_rectangle(
        tuple(value * S for value in box),
        radius=radius * S,
        fill=fill,
        outline=outline,
        width=width * S,
    )


def _pill(draw: ImageDraw.ImageDraw, x: int, code: str, country: str) -> None:
    width = 136 if len(country) <= 13 else 158
    _rounded(draw, (x, 110, x + width, 142), 16, SURFACE_2, BORDER)
    _rounded(draw, (x + 6, 116, x + 36, 136), 10, "#2C2C32")
    _text(draw, (x + 21, 126), code, 9, WHITE, "SemiBold", "mm")
    _text(draw, (x + 45, 126), country, 11, WHITE, "Medium", "lm")


def _fit_text(draw: ImageDraw.ImageDraw, value: str, size: int, max_width: int) -> str:
    font = _font(size)
    max_scaled = max_width * S
    if draw.textlength(value, font=font) <= max_scaled:
        return value
    words = value.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and draw.textlength(candidate, font=font) > max_scaled:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return "\n".join(lines[:3])


def _short_country(country: Country) -> str:
    if country.name == "United States":
        return "United States"
    if country.name == "United Kingdom":
        return "United Kingdom"
    return country.name


def render_ppp_card(result: PPPResult) -> BytesIO:
    """Render a crisp dark-mode PPP comparison card into a PNG buffer."""
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)

    source = result.source.country
    target = result.target.country
    source_amount = display_amount(result.amount, source.currency)
    market_amount = display_amount(result.market_amount, target.currency)
    ppp_amount = display_amount(result.purchasing_power_amount, target.currency)

    _text(draw, (45, 40), "PURCHASING POWER", 10, SECONDARY, "SemiBold")
    _text(draw, (45, 68), f"What does {source_amount} feel like?", 28, WHITE, "SemiBold")
    _pill(draw, 45, source.territory, _short_country(source))
    _text(draw, (400, 126), "→", 17, TERTIARY, anchor="mm")
    target_width = 136 if len(_short_country(target)) <= 13 else 158
    _pill(draw, 755 - target_width, target.territory, _short_country(target))

    _rounded(draw, (45, 165, 382, 335), 19, SURFACE, BORDER)
    _text(draw, (70, 193), "MARKET VALUE", 9, SECONDARY, "SemiBold")
    _text(draw, (70, 236), market_amount, 42, WHITE, "SemiBold")
    _text(draw, (70, 294), "What a currency exchange gives you", 11, SECONDARY)

    _rounded(draw, (417, 165, 755, 335), 19, "#102117", "#245D35")
    _text(draw, (442, 193), "HOUSEHOLD PURCHASING POWER", 9, GREEN, "SemiBold")
    _text(draw, (442, 236), f"≈ {ppp_amount}", 42, WHITE, "SemiBold")
    ratio = f"{result.purchasing_power_ratio:.1f}×"
    _rounded(draw, (641, 235, 724, 263), 14, "#1D3D29")
    _text(draw, (682, 250), ratio, 12, GREEN, "SemiBold", "mm")
    _text(draw, (442, 294), "Adjusted for national household prices", 11, "#A9CBB2")

    sentence = (
        f"To have roughly the same household purchasing power as {source_amount} "
        f"in {source.name}, you would need about {ppp_amount} in {target.name}."
    )
    wrapped = _fit_text(draw, sentence, 15, 710)
    _text(draw, (45, 385), wrapped, 15, SECONDARY, "Regular")
    line_count = wrapped.count("\n") + 1
    disclaimer_y = 385 + line_count * 23 + 11
    _text(draw, (45, disclaimer_y), "An estimate—not an exchange rate or personal budget.", 10, TERTIARY)

    year = min(result.source.year, result.target.year)
    _text(draw, (45, 511), f"{year} national household averages", 10, TERTIARY)
    _text(draw, (755, 511), "World Bank  ·  Frankfurter", 10, TERTIARY, anchor="ra")

    output = image.resize(
        (DISPLAY_WIDTH * OUTPUT_SCALE, DISPLAY_HEIGHT * OUTPUT_SCALE),
        Image.Resampling.LANCZOS,
    )
    buffer = BytesIO()
    output.save(buffer, "PNG", optimize=True)
    buffer.seek(0)
    return buffer
