"""Pillow renderer for Vocab Catch cards (locked "C+" holo design).

Premium collectible-card look: a rarity-tinted holographic frame around a
dark legible panel, a faded letter watermark for depth, Fraunces Black
hero word, a 5-pip rarity row, and rounded outer corners. Legendary cards
get a rainbow-rare frame plus corner flourishes and an outer glow.

House convention (see docs/architecture.md#image-rendering-pillow): the
whole canvas is rendered at the super-sample multiplier ``S`` — every
coordinate, size, radius, and offset is multiplied by ``S`` — then
LANCZOS-downsampled on export. Fonts are loaded directly at ``size * S``
(we do NOT reuse league's ``get_font``). Exported as RGBA PNG so the
rounded corners are transparent on Discord's dark theme.
"""
from __future__ import annotations

import colorsys
import contextlib
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import TypedDict

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_DIR = Path(__file__).resolve().parent / "fonts"

# Super-sample multiplier — render big, LANCZOS-downsample on export.
S = 4
# Final card size (logical px) — classic 2.5:3.5 trading-card ratio.
CARD_W, CARD_H = 360, 504

RARITY_NAMES = {1: "COMMON", 2: "UNCOMMON", 3: "RARE", 4: "EPIC", 5: "LEGENDARY"}

# Per-tier palette: accent (bright) + deep (gradient end).
RARITY_COLORS = {
    1: {"a": (148, 163, 184), "b": (100, 116, 139)},   # slate
    2: {"a": (52, 211, 153), "b": (16, 185, 129)},      # emerald
    3: {"a": (96, 165, 250), "b": (37, 99, 235)},       # blue
    4: {"a": (192, 132, 252), "b": (147, 51, 234)},     # violet
    5: {"a": (251, 191, 36), "b": (217, 119, 6)},       # gold (rainbow frame)
}


class Card(TypedDict):
    """Card metadata the renderer needs (rarity/POS/gender/id).

    The prompt word, answer language, and example come from a resolved
    ``CardView`` (see ``catch_logic.resolve_card``) so the renderer stays
    agnostic about which language is being shown.
    """

    card_id: int
    part_of_speech: str | None
    gender: str | None
    rarity: int


# Small language badge shown under the rarity name.
_LANG_BADGE = {"es": "ESPAÑOL", "en": "ENGLISH"}
# Answer-language hint shown on the spawn (hidden) state.
_ANSWER_HINT = {"es": "type the Spanish word", "en": "type the English word"}


# Vendored font files (SIL OFL).
_INTER = FONT_DIR / "Inter.ttf"
_SORA = FONT_DIR / "Sora.ttf"
_FRAUNCES = FONT_DIR / "Fraunces.ttf"
_SPECTRAL_IT = FONT_DIR / "Spectral-Italic.ttf"


@lru_cache(maxsize=64)
def _font(path: str, size: int, variation: str | None = None) -> ImageFont.FreeTypeFont:
    """Load a font at ``size * S``; optionally select a named weight."""
    f = ImageFont.truetype(path, size * S)
    if variation:
        with contextlib.suppress(OSError):
            f.set_variation_by_name(variation)  # static/missing instance -> as-is
    return f


def _ctext(draw, cx, y, text, font, fill, anchor="mm", spacing=0):
    """Center text at (cx, y); optional manual letter-spacing for caps labels."""
    if spacing and len(text) > 1:
        total = sum(draw.textlength(ch, font=font) for ch in text)
        total += spacing * (len(text) - 1)
        x = cx - total / 2
        for ch in text:
            draw.text((x, y), ch, font=font, fill=fill, anchor="lm")
            x += draw.textlength(ch, font=font) + spacing
    else:
        draw.text((cx, y), text, font=font, fill=fill, anchor=anchor)


def _wrap_center(draw, cx, y, text, font, fill, max_w, line_h, max_lines=3):
    """Word-wrap ``text`` to ``max_w`` and draw centered lines from ``y``."""
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = w
            if len(lines) == max_lines:
                break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    for i, line in enumerate(lines):
        _ctext(draw, cx, y + i * line_h, line, font, fill)


def _hero_size(word: str) -> int:
    """Auto-shrink the hero word so long entries still fit."""
    n = len(word)
    if n <= 11:
        return 44
    if n <= 15:
        return 36
    return 28


def render_card(card: Card, view: dict, *, revealed: bool) -> BytesIO:
    """Render a card to a PNG ``BytesIO`` (RGBA, rounded corners).

    ``view`` is a resolved ``CardView`` (catch_logic.resolve_card): it
    supplies the ``prompt`` word shown, the ``prompt_lang`` / ``answer_lang``
    badges, and the prompt-language ``example``. ``card`` supplies the
    rarity/POS/gender/id metadata.

    ``revealed=False`` is the spawn state (answer/example hidden);
    ``revealed=True`` is the caught/collection state.
    """
    w, h = CARD_W * S, CARD_H * S
    rarity = max(1, min(5, int(card["rarity"])))
    pal = RARITY_COLORS[rarity]
    a, b = pal["a"], pal["b"]
    rainbow = rarity == 5

    # 1) Holo frame: rarity gradient + faint sheen/dots (foil shines on light).
    img = Image.new("RGB", (w, h), a)
    fd = ImageDraw.Draw(img)
    if rainbow:
        for yy in range(h):
            hue = (yy / h) * 0.85  # red -> violet sweep
            cr, cg, cb = colorsys.hsv_to_rgb(hue, 0.55, 1.0)
            fd.line([(0, yy), (w, yy)], fill=(int(cr * 255), int(cg * 255), int(cb * 255)))
    else:
        for yy in range(h):
            t = yy / h
            fd.line([(0, yy), (w, yy)],
                    fill=tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3)))
    sheen = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sheen)
    for i in range(-h, w, 30 * S):
        sd.line([(i, 0), (i + h, h)], fill=(255, 255, 255, 22), width=10 * S)
    for yy in range(0, h, 14 * S):
        for xx in range(0, w, 14 * S):
            sd.ellipse([xx, yy, xx + 3 * S, yy + 3 * S], fill=(255, 255, 255, 16))
    img = Image.alpha_composite(img.convert("RGBA"), sheen).convert("RGB")

    # 2) Dark content panel (rounded), inset to reveal the holo frame.
    inset = 14 * S
    panel = Image.new("RGBA", (w - inset * 2, h - inset * 2), (16, 17, 22, 255))
    pmask = Image.new("L", panel.size, 0)
    ImageDraw.Draw(pmask).rounded_rectangle(
        [0, 0, panel.size[0] - 1, panel.size[1] - 1], radius=22 * S, fill=255)

    # 2b) Watermark: giant faded first letter (article ignored) behind the hero.
    prompt_word = view["prompt"]
    wm = Image.new("RGBA", panel.size, (0, 0, 0, 0))
    tokens = prompt_word.split()
    last_token = tokens[-1] if tokens else prompt_word
    letter = (last_token[:1] or "?").upper()
    ImageDraw.Draw(wm).text(
        (panel.size[0] // 2, int(panel.size[1] * 0.42)), letter,
        font=_font(str(_FRAUNCES), 150, "Black"), fill=(*a, 26), anchor="mm")
    panel = Image.alpha_composite(panel, wm)
    img.paste(panel.convert("RGB"), (inset, inset), pmask)

    # Epic/Legendary outer glow.
    if rarity >= 4:
        glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(glow).rounded_rectangle(
            [6 * S, 6 * S, w - 6 * S, h - 6 * S], radius=30 * S,
            outline=(*a, 255), width=3 * S)
        glow = glow.filter(ImageFilter.GaussianBlur(7 * S))
        img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")

    d = ImageDraw.Draw(img)
    cx = w // 2
    px0, px1 = inset + 18 * S, w - inset - 18 * S

    # 3) Header: rarity name + language badge + 5-pip row.
    _ctext(d, cx, inset + 26 * S, RARITY_NAMES[rarity], _font(str(_INTER), 11, "Bold"),
           a, spacing=4 * S)
    badge = _LANG_BADGE.get(view["prompt_lang"], "")
    if badge:
        _ctext(d, cx, inset + 44 * S, badge, _font(str(_INTER), 9, "SemiBold"),
               (120, 126, 138), spacing=3 * S)
    pip_y = inset + 62 * S
    pr, gap = 4 * S, 16 * S
    start = cx - (gap * 4) / 2
    for i in range(5):
        col = a if i < rarity else (70, 74, 84)
        d.ellipse([start + i * gap - pr, pip_y - pr, start + i * gap + pr, pip_y + pr],
                  fill=col)

    # 4) Hero word (Fraunces Black) — the prompt-language word.
    _ctext(d, cx, int(h * 0.40), prompt_word,
           _font(str(_FRAUNCES), _hero_size(prompt_word), "Black"), (245, 246, 250))

    # gender · part-of-speech chip
    bits = [x for x in (card.get("gender"), card.get("part_of_speech")) if x]
    if bits:
        _ctext(d, cx, int(h * 0.475), "  ·  ".join(bits),
               _font(str(_INTER), 11, "Medium"), (150, 156, 168), spacing=1 * S)

    # divider
    d.line([(cx - 64 * S, int(h * 0.535)), (cx + 64 * S, int(h * 0.535))], fill=a,
           width=2 * S)

    # 5) Answer + example (hidden until caught).
    if revealed:
        _ctext(d, cx, int(h * 0.605), view["answer"],
               _font(str(_SORA), 22, "SemiBold"), a)
        if view.get("example"):
            _wrap_center(d, cx, int(h * 0.71), view["example"],
                         _font(str(_SPECTRAL_IT), 13), (165, 170, 182),
                         max_w=px1 - px0, line_h=21 * S)
    else:
        _ctext(d, cx, int(h * 0.605), "• • •", _font(str(_SORA), 24, "Bold"),
               (95, 100, 112))
        hint = _ANSWER_HINT.get(view["answer_lang"], "type the word")
        _ctext(d, cx, int(h * 0.70), f"catch — {hint}",
               _font(str(_INTER), 11, "Medium"), (110, 116, 128), spacing=1 * S)

    # 6) Footer: card number.
    _ctext(d, cx, h - inset - 26 * S, f"#{card['card_id']:04d}",
           _font(str(_INTER), 11, "SemiBold"), (110, 116, 128), spacing=2 * S)

    # Legendary corner flourishes.
    if rarity == 5:
        for (ox, oy, dx, dy) in (
            (inset + 22 * S, inset + 22 * S, 1, 1),
            (w - inset - 22 * S, inset + 22 * S, -1, 1),
            (inset + 22 * S, h - inset - 22 * S, 1, -1),
            (w - inset - 22 * S, h - inset - 22 * S, -1, -1),
        ):
            length = 16 * S
            d.line([(ox, oy), (ox + dx * length, oy)], fill=a, width=2 * S)
            d.line([(ox, oy), (ox, oy + dy * length)], fill=a, width=2 * S)

    # 7) Downsample + round the outer corners (transparent PNG).
    out = img.resize((CARD_W, CARD_H), Image.Resampling.LANCZOS).convert("RGBA")
    corner = Image.new("L", (CARD_W, CARD_H), 0)
    ImageDraw.Draw(corner).rounded_rectangle(
        [0, 0, CARD_W - 1, CARD_H - 1], radius=26, fill=255)
    out.putalpha(corner)

    buf = BytesIO()
    out.save(buf, format="PNG")
    buf.seek(0)
    return buf
