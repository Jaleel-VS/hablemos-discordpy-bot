"""Word of the Day card renderer — Pillow-based image generation.

House convention (docs/architecture.md#image-rendering-pillow): render at
super-sample multiplier ``S``, then LANCZOS-downsample on export. Every
coordinate/size/offset is multiplied by ``S``.
"""
from __future__ import annotations

import contextlib
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Re-use fonts from vocabcatch_cog (same OFL-licensed font set)
FONT_DIR = Path(__file__).resolve().parent.parent / "vocabcatch_cog" / "fonts"

# Super-sample multiplier
S = 3
# Card dimensions (logical px) — wide card for sentence examples
CARD_W, CARD_H = 480, 280


# -- Palettes per card type --
PALETTES = {
    "beginner_en": {
        "bg": (30, 41, 59),       # slate-800
        "accent": (52, 211, 153), # emerald-400
        "label": "BEGINNER",
        "lang": "ENGLISH",
    },
    "beginner_es": {
        "bg": (30, 41, 59),
        "accent": (251, 191, 36),  # amber-400
        "label": "PRINCIPIANTE",
        "lang": "ESPANOL",
    },
    "advanced_en": {
        "bg": (15, 23, 42),        # slate-900
        "accent": (96, 165, 250),  # blue-400
        "label": "ADVANCED",
        "lang": "ENGLISH",
    },
    "advanced_es": {
        "bg": (15, 23, 42),
        "accent": (192, 132, 252), # violet-400
        "label": "AVANZADO",
        "lang": "ESPANOL",
    },
}


@lru_cache(maxsize=32)
def _font(name: str, size: int, variation: str | None = None) -> ImageFont.FreeTypeFont:
    """Load a font at size * S."""
    path = FONT_DIR / name
    f = ImageFont.truetype(str(path), size * S)
    if variation:
        with contextlib.suppress(OSError):
            f.set_variation_by_name(variation)
    return f


def _draw_rounded_rect(img: Image.Image, radius: int, bg: tuple[int, ...]) -> Image.Image:
    """Apply rounded corners to a card image."""
    r = radius * S
    mask = Image.new("L", img.size, 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([(0, 0), (img.width - 1, img.height - 1)], radius=r, fill=255)
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.paste(img, mask=mask)
    return out


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    """Word-wrap text to fit within max_w pixels."""
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def render_wotd_card(
    card_type: str,
    word: str,
    translation: str,
    example: str,
) -> BytesIO:
    """Render a WOTD card to PNG BytesIO.

    Parameters
    ----------
    card_type: One of 'beginner_en', 'beginner_es', 'advanced_en', 'advanced_es'
    word: The word of the day
    translation: Translation of the word
    example: Example sentence using the word
    """
    pal = PALETTES[card_type]
    bg = pal["bg"]
    accent = pal["accent"]
    label = pal["label"]
    lang = pal["lang"]

    w, h = CARD_W * S, CARD_H * S
    img = Image.new("RGB", (w, h), bg)
    draw = ImageDraw.Draw(img)

    # Subtle gradient overlay from top
    for yy in range(h // 3):
        draw.line([(0, yy), (w, yy)], fill=(accent[0], accent[1], accent[2]))
    # Redraw with proper alpha — just do a lighter band at top
    img2 = Image.new("RGB", (w, h), bg)
    draw2 = ImageDraw.Draw(img2)
    for yy in range(h // 4):
        t = 1 - yy / (h // 4)
        r = int(bg[0] + (accent[0] - bg[0]) * t * 0.12)
        g = int(bg[1] + (accent[1] - bg[1]) * t * 0.12)
        b = int(bg[2] + (accent[2] - bg[2]) * t * 0.12)
        draw2.line([(0, yy), (w, yy)], fill=(r, g, b))
    # Fill rest with bg
    draw2.rectangle([(0, h // 4), (w, h)], fill=bg)
    img = img2
    draw = ImageDraw.Draw(img)

    # Accent bar on left
    bar_w = 6 * S
    draw.rectangle([(0, 0), (bar_w, h)], fill=accent)

    # Margins
    mx = 28 * S  # left margin (after bar)
    top = 24 * S

    # -- Header: level label + language badge --
    font_label = _font("Sora.ttf", 11, "Bold")
    draw.text((mx, top), label, font=font_label, fill=accent)

    font_lang = _font("Inter.ttf", 9)
    lang_y = top + 16 * S
    draw.text((mx, lang_y), lang, font=font_lang, fill=(148, 163, 184))

    # -- Hero word --
    word_size = 36 if len(word) <= 12 else (28 if len(word) <= 18 else 22)
    font_word = _font("Fraunces.ttf", word_size, "Black")
    word_y = top + 44 * S
    draw.text((mx, word_y), word, font=font_word, fill=(255, 255, 255))

    # -- Translation --
    font_trans = _font("Inter.ttf", 14)
    trans_y = word_y + (word_size + 10) * S
    draw.text((mx, trans_y), translation, font=font_trans, fill=accent)

    # -- Divider line --
    div_y = trans_y + 24 * S
    draw.line([(mx, div_y), (w - mx, div_y)], fill=(51, 65, 85), width=1 * S)

    # -- Example sentence --
    font_ex = _font("Spectral-Italic.ttf", 13)
    ex_y = div_y + 14 * S
    max_text_w = w - mx * 2
    lines = _wrap_text(draw, f'"{example}"', font_ex, max_text_w)
    line_h = 18 * S
    for i, line in enumerate(lines[:3]):
        draw.text((mx, ex_y + i * line_h), line, font=font_ex, fill=(203, 213, 225))

    # -- Round corners + export --
    img_rgba = img.convert("RGBA")
    img_rounded = _draw_rounded_rect(img_rgba, 16, bg)

    # Downsample
    final = img_rounded.resize((CARD_W, CARD_H), Image.Resampling.LANCZOS)

    buf = BytesIO()
    final.save(buf, format="PNG")
    buf.seek(0)
    return buf
