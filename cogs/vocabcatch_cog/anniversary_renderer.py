"""Pillow renderer for the 10-year anniversary Vocab Catch cards.

Two typographic designs — no illustrations, so there is nothing to
license and no generated art:

- **Sello** (common tier): a perforated postage stamp. The hero is the
  word itself in Fraunces Black, with its article in a pill, a syllable
  line (stressed syllable bold caps), and a banknote guilloche rosette
  behind it. Caught cards are cancelled with a ``10 AÑOS`` postmark.
- **Tinta** (rare tier): an ink tabletop card. The hero is the word's
  initial as a hatched wood-type capital with a coral offset shadow, on
  a faint sunburst, bleeding into a black panel with the bilingual
  example.

Each card's plate colour, rosette, sunburst and splatter are seeded from
``card_id``, so a card always renders the same and no two cards match.

House convention (docs/architecture.md#image-rendering-pillow): the whole
canvas is drawn at ``S`` times the 360×504 card. Every coordinate and
font size below is already expressed in S-scaled pixels (nominal × S),
like ``league_cog/.../round_end_image.py``; fonts are loaded at those
literal sizes (not via league's ``get_font``). Output is an RGBA PNG.
"""
from __future__ import annotations

import contextlib
import math
import random
from datetime import date
from functools import lru_cache
from io import BytesIO
from typing import TypedDict

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageMath

from .catch_logic import CardView, points_for, split_article
from .renderer import CARD_H, CARD_W, FONT_DIR
from .syllables import stressed_index, syllabify

S = 3
W, H = CARD_W * S, CARD_H * S

_FRAUNCES = str(FONT_DIR / "Fraunces.ttf")
_SORA = str(FONT_DIR / "Sora.ttf")
_SPECTRAL_IT = str(FONT_DIR / "Spectral-Italic.ttf")

SERVER_NAME = ("SPANISH · ENGLISH", "LEARNING SERVER")
ANNIVERSARY = "10 AÑOS"

_HINT = {"es": "type the Spanish word", "en": "type the English word"}
_MONTHS_ES = ("ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO", "SEP", "OCT", "NOV", "DIC")
_POS_ABBR = {"sustantivo": "SUST.", "verbo": "VERBO", "adjetivo": "ADJ.", "adverbio": "ADV."}
_GENDER_ABBR = {"el": "MASC.", "la": "FEM."}

type RGB = tuple[int, int, int]

# Sello plate colours (one picked per card).
_PLATES: tuple[RGB, ...] = (
    (52, 102, 76), (160, 36, 50), (40, 70, 130), (150, 84, 32), (92, 52, 110),
)
_STAMP_PAPER: RGB = (246, 240, 226)
_CREAM: RGB = (248, 236, 210)
_WINDOW: RGB = (247, 238, 218)

# Tinta palette.
_CORAL: RGB = (214, 98, 82)
_INK_PAPER: RGB = (234, 233, 230)
_BLACK: RGB = (14, 14, 15)
_FOOTER_GRAY: RGB = (120, 120, 118)


class AnniversaryCard(TypedDict):
    """Pool row fields the anniversary renderers read (see ``get_card``)."""

    card_id: int
    word_es: str
    word_en: str
    part_of_speech: str | None
    gender: str | None
    example_es: str | None
    example_en: str | None
    rarity: int


# ── primitives ──────────────────────────────────────────────────────────────

@lru_cache(maxsize=64)
def _font(path: str, px: int, variation: str | None = None) -> ImageFont.FreeTypeFont:
    """Load a font at a literal (already S-scaled) pixel size."""
    f = ImageFont.truetype(path, px)
    if variation:
        with contextlib.suppress(OSError):
            f.set_variation_by_name(variation)
    return f


def _fit(path: str, variation: str | None, text: str, max_w: float, start: int,
         floor: int = 24) -> ImageFont.FreeTypeFont:
    """Largest font ≤ ``start`` px whose rendering of ``text`` fits ``max_w``."""
    size = start
    while size > floor:
        f = _font(path, size, variation)
        if f.getlength(text) <= max_w:
            return f
        size -= 4
    return _font(path, floor, variation)


def _trim(text: str, f: ImageFont.FreeTypeFont, max_w: float) -> str:
    """Ellipsize ``text`` to ``max_w`` (only hit by very long examples)."""
    if f.getlength(text) <= max_w:
        return text
    while text and f.getlength(text + "…") > max_w:
        text = text[:-1]
    return text.rstrip() + "…"


def _spaced(d: ImageDraw.ImageDraw, cx: float, y: float, text: str,
            f: ImageFont.FreeTypeFont, fill: RGB, track: int) -> None:
    """Centre letter-spaced caps at (cx, y)."""
    widths = [f.getlength(c) for c in text]
    x = cx - (sum(widths) + track * (len(text) - 1)) / 2
    for c, w in zip(text, widths, strict=True):
        d.text((x, y), c, font=f, fill=fill, anchor="lm")
        x += w + track


def _lerp(a: RGB, b: RGB, t: float) -> RGB:
    return (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t),
            int(a[2] + (b[2] - a[2]) * t))


def _grain(img: Image.Image, amount: int) -> Image.Image:
    """Overlay faint paper grain, keeping alpha."""
    noise = Image.effect_noise(img.size, 40).convert("L")
    noise = noise.point([128 + (v - 128) * amount // 40 for v in range(256)])
    out = ImageChops.overlay(img.convert("RGB"), Image.merge("RGB", (noise, noise, noise))).convert("RGBA")
    out.putalpha(img.getchannel("A"))
    return out


def _export(img: Image.Image, *, rounded: bool) -> BytesIO:
    out = img.resize((CARD_W, CARD_H), Image.Resampling.LANCZOS)
    if rounded:
        corner = Image.new("L", out.size, 0)
        ImageDraw.Draw(corner).rounded_rectangle([0, 0, CARD_W - 1, CARD_H - 1], radius=18, fill=255)
        out.putalpha(ImageChops.multiply(out.getchannel("A"), corner))
    buf = BytesIO()
    out.save(buf, "PNG")
    buf.seek(0)
    return buf


def _syllable_line(d: ImageDraw.ImageDraw, cx: float, y: float, word: str,
                   normal: RGB, stressed: RGB, sep: RGB, size: int) -> None:
    """``ma · ri · PO · sa`` with the stressed syllable bold, caps, coloured."""
    syl = syllabify(word)
    if len(syl) < 2:
        return
    stress = stressed_index(syl)
    f_norm, f_bold = _font(_SORA, size, "Bold"), _font(_SORA, size + 4, "ExtraBold")
    parts: list[tuple[str, ImageFont.FreeTypeFont, RGB]] = []
    for i, s in enumerate(syl):
        parts.append((s.upper(), f_bold, stressed) if i == stress else (s, f_norm, normal))
        if i < len(syl) - 1:
            parts.append(("  ·  ", f_norm, sep))
    x = cx - sum(f.getlength(t) for t, f, _ in parts) / 2
    for t, f, col in parts:
        d.text((x, y), t, font=f, fill=col, anchor="ls")
        x += f.getlength(t)


def _guilloche(size: tuple[int, int], color: RGB, rng: random.Random) -> Image.Image:
    """Banknote rosette: nested hypotrochoids with card-seeded ratios."""
    im = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx, cy = size[0] / 2, size[1] / 2
    big = min(size) * 0.46
    R = int(big * rng.uniform(0.8, 0.95))
    r = max(1, R // rng.choice((13, 17, 19, 23)))
    dd = r * rng.uniform(2.2, 3.4)
    turns = r // math.gcd(R, r)
    steps = 600 * turns
    for ring in range(5):
        k = (1 - ring * 0.13) * big / (R - r + dd)
        pts = []
        for i in range(steps):
            t = i / steps * 2 * math.pi * turns
            pts.append((cx + k * ((R - r) * math.cos(t) + dd * math.cos((R - r) / r * t)),
                        cy + k * ((R - r) * math.sin(t) - dd * math.sin((R - r) / r * t))))
        d.line([*pts, pts[0]], fill=color, width=2)
    return im


def _rays(size: tuple[int, int], color: RGB, rng: random.Random) -> Image.Image:
    """Faint sunburst centred slightly off the middle."""
    im = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    n = rng.choice((18, 24, 32))
    cx, cy = size[0] / 2, size[1] * rng.uniform(0.35, 0.5)
    R = max(size) * 1.5
    off = rng.random() * math.pi
    for k in range(n):
        a0, a1 = off + 2 * math.pi * k / n, off + 2 * math.pi * (k + 0.5) / n
        d.polygon([(cx, cy), (cx + R * math.cos(a0), cy + R * math.sin(a0)),
                   (cx + R * math.cos(a1), cy + R * math.sin(a1))], fill=color)
    return im


def _text_mask(size: tuple[int, int], xy: tuple[float, float], text: str,
               f: ImageFont.FreeTypeFont, stroke: int = 0) -> Image.Image:
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).text(xy, text, font=f, fill=255, anchor="mm", stroke_width=stroke, stroke_fill=255)
    return m


def _hatch(size: tuple[int, int], spacing: int, width: int, angle: float) -> Image.Image:
    big = int(math.hypot(*size)) + spacing * 2
    im = Image.new("L", (big, big), 0)
    d = ImageDraw.Draw(im)
    for x in range(0, big, spacing):
        d.line([(x, 0), (x, big)], fill=255, width=width)
    im = im.rotate(angle, resample=Image.Resampling.BICUBIC)
    left, top = (big - size[0]) // 2, (big - size[1]) // 2
    return im.crop((left, top, left + size[0], top + size[1]))


def _postmark(on: date, ink: tuple[int, int, int, int]) -> Image.Image:
    """Round ``10 AÑOS`` cancel with the catch date and wavy bars."""
    pm = Image.new("RGBA", (760, 320), (0, 0, 0, 0))
    d = ImageDraw.Draw(pm)
    cx, cy, r = 160, 160, 140
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=ink, width=8)
    d.ellipse([cx - r + 20, cy - r + 20, cx + r - 20, cy + r - 20], outline=ink, width=3)
    d.text((cx, cy - 34), ANNIVERSARY, font=_font(_SORA, 44, "ExtraBold"), fill=ink, anchor="mm")
    d.line([(cx - 92, cy + 4), (cx + 92, cy + 4)], fill=ink, width=4)
    stamp = f"{on.day:02d}·{_MONTHS_ES[on.month - 1]}·{on.year % 100:02d}"
    d.text((cx, cy + 44), stamp, font=_font(_SORA, 34, "ExtraBold"), fill=ink, anchor="mm")
    for k in range(4):
        y0 = cy - 75 + k * 50
        d.line([(cx + r + 14 + x, y0 + 12 * math.sin(x / 34)) for x in range(0, 440, 8)], fill=ink, width=7)
    rough = Image.effect_noise(pm.size, 90).convert("L").point([255 if v > 92 else 0 for v in range(256)])
    pm.putalpha(ImageChops.multiply(pm.getchannel("A"), rough))
    return pm.rotate(-8, resample=Image.Resampling.BICUBIC, expand=True)


def _perforate(img: Image.Image) -> None:
    """Punch stamp perforations into the canvas edge (in place)."""
    mask = Image.new("L", img.size, 255)
    d = ImageDraw.Draw(mask)
    r, step = 20, 60
    for x in range(step // 2, W, step):
        d.ellipse([x - r, -r, x + r, r], fill=0)
        d.ellipse([x - r, H - r, x + r, H + r], fill=0)
    for y in range(step // 2, H, step):
        d.ellipse([-r, y - r, r, y + r], fill=0)
        d.ellipse([W - r, y - r, W + r, y + r], fill=0)
    img.putalpha(ImageChops.multiply(img.getchannel("A"), mask))


def _ink_bleed(height: int) -> Image.Image:
    """Ragged, clumpy edge mask: transparent at the top, solid at the bottom."""
    ramp = Image.linear_gradient("L").resize((W, height)).convert("F")
    clump = Image.effect_noise((W, height), 64).filter(ImageFilter.GaussianBlur(7)).convert("F")
    wave = Image.effect_noise((W // 90 + 2, 1), 64).resize((W, height), Image.Resampling.BICUBIC).convert("F")
    field = ImageMath.lambda_eval(
        lambda a: (a["r"] * (2.2 / 255) + (a["c"] - 128) * (1.6 / 255) + (a["w"] - 128) * (0.25 / 255) - 1.0)
        * 3060,
        r=ramp, c=clump, w=wave,
    )
    return field.convert("L")


# ── shared text logic ───────────────────────────────────────────────────────

def _translation(card: AnniversaryCard, view: CardView) -> str:
    """The other-language word, shown once the card is caught."""
    return card["word_en"] if view["prompt_lang"] == "es" else card["word_es"]


def _examples(card: AnniversaryCard, view: CardView, *, revealed: bool) -> list[tuple[str, str]]:
    """``[(lang, sentence), …]`` — prompt language only while wild (no answer leak)."""
    by_lang = {"es": card.get("example_es"), "en": card.get("example_en")}
    order = [view["prompt_lang"]] + ([("en" if view["prompt_lang"] == "es" else "es")] if revealed else [])
    return [(lang, text) for lang in order if (text := by_lang[lang])]


def _pos_label(card: AnniversaryCard) -> str:
    pos = (card.get("part_of_speech") or "").casefold()
    parts = [_POS_ABBR.get(pos, pos.upper())] if pos else []
    if gender := _GENDER_ABBR.get((card.get("gender") or "").casefold()):
        parts.append(gender)
    return " ".join(parts)


# ── Sello (common) ──────────────────────────────────────────────────────────

def render_stamp(card: AnniversaryCard, view: CardView, *, revealed: bool,
                 caught_on: date | None = None) -> BytesIO:
    """Render the Sello stamp. ``revealed`` adds the translation + postmark."""
    rng = random.Random(card["card_id"])
    plate = rng.choice(_PLATES)
    img = Image.new("RGBA", (W, H), (*_STAMP_PAPER, 255))
    d = ImageDraw.Draw(img)

    m = 74
    px0, py0, px1, py1 = m, m, W - m, H - m
    lines = Image.new("RGBA", (px1 - px0, py1 - py0), (*plate, 255))
    ld = ImageDraw.Draw(lines)
    engraved = _lerp(plate, (0, 0, 0), 0.22)
    for y in range(0, lines.height, 9):
        ld.line([(0, y), (lines.width, y)], fill=engraved, width=2)
    img.alpha_composite(lines, (px0, py0))
    d.rectangle([px0 + 22, py0 + 22, px1 - 22, py1 - 22], outline=_CREAM, width=4)
    _spaced(d, W / 2, py0 + 92, SERVER_NAME[0], _font(_SORA, 50, "ExtraBold"), _CREAM, 10)
    _spaced(d, W / 2, py0 + 150, SERVER_NAME[1], _font(_SORA, 24, "Bold"), _lerp(_CREAM, plate, 0.25), 14)

    # Window: rosette, article pill, hero word, syllables, translation.
    vx0, vy0, vx1, vy1 = px0 + 64, py0 + 200, px1 - 64, py0 + 930
    d.rectangle([vx0 - 14, vy0 - 14, vx1 + 14, vy1 + 14], fill=_CREAM)
    d.rectangle([vx0, vy0, vx1, vy1], fill=_WINDOW)
    img.alpha_composite(_guilloche((vx1 - vx0, vy1 - vy0), _lerp(_WINDOW, plate, 0.16), rng), (vx0, vy0))
    d.rectangle([vx0 + 18, vy0 + 18, vx1 - 18, vy1 - 18], outline=_lerp(_WINDOW, plate, 0.5), width=3)

    cx = (vx0 + vx1) / 2
    article, bare = split_article(view["prompt"], view["prompt_lang"])
    if article:
        pill_f = _font(_SORA, 34, "ExtraBold")
        pw = pill_f.getlength(article.upper()) + 50
        d.rounded_rectangle([cx - pw / 2, vy0 + 80, cx + pw / 2, vy0 + 140], radius=30, fill=plate)
        d.text((cx, vy0 + 111), article.upper(), font=pill_f, fill=_WINDOW, anchor="mm")
    hero = _fit(_FRAUNCES, "Black", bare, vx1 - vx0 - 110, 230, floor=60)
    d.text((cx, vy0 + 330), bare, font=hero, fill=plate, anchor="mm")
    if view["prompt_lang"] == "es":
        _syllable_line(d, cx, vy0 + 500, bare, _lerp(plate, _WINDOW, 0.45), plate,
                       _lerp(plate, _WINDOW, 0.6), 40)
    d.line([(cx - 200, vy0 + 560), (cx + 200, vy0 + 560)], fill=_lerp(_WINDOW, plate, 0.4), width=3)
    under = _translation(card, view) if revealed else _HINT[view["answer_lang"]]
    under_f = _fit(_SPECTRAL_IT, None, under, vx1 - vx0 - 110, 62)
    d.text((cx, vy0 + 630), under, font=under_f, fill=_lerp(plate, _WINDOW, 0.2), anchor="mm")

    # Examples below the window.
    for i, (_, text) in enumerate(_examples(card, view, revealed=revealed)):
        size, col = (48, _CREAM) if i == 0 else (40, _lerp(_CREAM, plate, 0.35))
        f = _fit(_SPECTRAL_IT, None, text, px1 - px0 - 140, size, floor=28)
        d.text((W / 2, py0 + 1020 + i * 60), _trim(text, f, px1 - px0 - 140), font=f, fill=col, anchor="mm")

    # Footer: number · SELLO · points.
    fy = py1 - 96
    d.text((px0 + 64, fy), f"Nº {card['card_id']:03d}", font=_font(_SORA, 32, "ExtraBold"), fill=_CREAM,
           anchor="lm")
    _spaced(d, W / 2, fy, "SELLO", _font(_SORA, 30, "ExtraBold"), _CREAM, 12)
    pts = str(points_for(card["rarity"]))
    pts_f = _font(_FRAUNCES, 96, "Black")
    d.text((px1 - 64, fy + 6), pts, font=pts_f, fill=_CREAM, anchor="rs")
    d.text((px1 - 64 - pts_f.getlength(pts) - 12, fy + 4), "PTS", font=_font(_SORA, 22, "ExtraBold"),
           fill=_CREAM, anchor="rs")

    if revealed:
        pm = _postmark(caught_on or date.today(), (40, 24, 20, 200))
        img.alpha_composite(pm, (int(vx1 - 190), int(vy1 - 175)))

    img = _grain(img, 8)
    _perforate(img)
    return _export(img, rounded=False)


# ── Tinta (rare) ────────────────────────────────────────────────────────────

def render_ink(card: AnniversaryCard, view: CardView, *, revealed: bool) -> BytesIO:
    """Render the Tinta ink card. ``revealed`` swaps the hint for the translation."""
    rng = random.Random(card["card_id"])
    img = Image.new("RGBA", (W, H), (*_INK_PAPER, 255))
    d = ImageDraw.Draw(img)

    art_top, art_bot = 230, 1240
    aw, ah = W, art_bot - art_top
    img.alpha_composite(_rays((aw, ah), _lerp(_INK_PAPER, _BLACK, 0.06), rng), (0, art_top))

    # Hero: hatched initial with a coral offset shadow + a few splatters.
    _, bare = split_article(view["prompt"], view["prompt_lang"])
    letter = next((ch for ch in bare if ch.isalpha()), "?").upper()
    lf = _font(_FRAUNCES, 720, "Black")
    lx, ly = aw / 2 + rng.randint(-30, 30), ah * 0.40
    shadow = Image.new("RGBA", (aw, ah), (*_CORAL, 255))
    shadow.putalpha(_text_mask((aw, ah), (lx + 34, ly + 34), letter, lf))
    body = _text_mask((aw, ah), (lx, ly), letter, lf)
    outline = ImageChops.subtract(_text_mask((aw, ah), (lx, ly), letter, lf, stroke=12), body)
    lower_half = Image.linear_gradient("L").resize((aw, ah)).point(
        [max(0, min(255, (v - 115) * 3)) for v in range(256)])
    shade = ImageChops.lighter(_hatch((aw, ah), 18, 7, rng.choice((35, 45, 55))),
                               ImageChops.multiply(_hatch((aw, ah), 18, 6, -45), lower_half))
    fill = Image.new("RGBA", (aw, ah), (*_INK_PAPER, 255))
    fill.putalpha(body)
    ink = Image.new("RGBA", (aw, ah), (*_BLACK, 255))
    ink.putalpha(ImageChops.lighter(ImageChops.multiply(shade, body), outline))
    layer = Image.new("RGBA", (aw, ah), (0, 0, 0, 0))
    for part in (shadow, fill, ink):
        layer.alpha_composite(part)
    sd = ImageDraw.Draw(layer)
    for _ in range(rng.randint(2, 3)):
        sx, sy = rng.uniform(0.1, 0.9) * aw, rng.uniform(0.15, 0.65) * ah
        col = _CORAL if rng.random() < 0.7 else _BLACK
        for _ in range(rng.randint(8, 16)):
            rr = abs(rng.gauss(0, 1)) * 6 + 2
            px, py = sx + rng.gauss(0, 60), sy + rng.gauss(0, 60)
            sd.ellipse([px - rr, py - rr, px + rr, py + rr], fill=col)
    img.alpha_composite(layer, (0, art_top))

    if view["prompt_lang"] == "es":
        _syllable_line(d, W / 2, art_bot - 225, bare, _lerp(_BLACK, _INK_PAPER, 0.4), _CORAL,
                       _lerp(_BLACK, _INK_PAPER, 0.55), 40)

    bleed_h = 210
    black = Image.new("RGBA", (W, bleed_h), (*_BLACK, 255))
    black.putalpha(_ink_bleed(bleed_h))
    img.alpha_composite(black, (0, art_bot - bleed_h))
    d.rectangle([0, art_bot, W, H], fill=_BLACK)

    # Bookmark tab: points + star.
    tx0, tx1 = 70, 220
    tcx = (tx0 + tx1) / 2
    d.rounded_rectangle([tx0, -40, tx1, 330], radius=26, fill=_BLACK)
    d.text((tcx, 105), str(points_for(card["rarity"])), font=_font(_FRAUNCES, 104, "Black"), fill=_INK_PAPER,
           anchor="mm")
    d.polygon([(tcx + (46 if k % 2 == 0 else 21) * math.cos(-math.pi / 2 + k * math.pi / 5),
                245 + (46 if k % 2 == 0 else 21) * math.sin(-math.pi / 2 + k * math.pi / 5)) for k in range(10)],
              fill=_CORAL)

    # Title + coral subline.
    title_f = _fit(_FRAUNCES, "Bold", view["prompt"], W - 2 * 280, 92, floor=44)
    d.text((W / 2 + 60, 112), view["prompt"], font=title_f, fill=_BLACK, anchor="mm")
    if revealed:
        sub = "  ·  ".join(p for p in (_translation(card, view).upper(), _pos_label(card)) if p)
    else:
        sub = f"ATRÁPALA  ·  {_HINT[view['answer_lang']].upper()}"
    sub_f = _fit(_FRAUNCES, "Bold", sub, W - 2 * 250, 30, floor=20)
    _spaced(d, W / 2 + 60, 190, sub, sub_f, _CORAL, 3)

    # Divider chips: prompt → answer language.
    dy, chip, gap = 1275, 76, 26
    x0 = W / 2 - (chip * 3 + gap * 2) / 2
    d.line([(90, dy), (x0 - 30, dy)], fill=_INK_PAPER, width=4)
    d.line([(x0 + chip * 3 + gap * 2 + 30, dy), (W - 90, dy)], fill=_INK_PAPER, width=4)
    chip_f = _font(_SORA, 28, "ExtraBold")
    for i, lab in enumerate((view["prompt_lang"].upper(), "", view["answer_lang"].upper())):
        x = x0 + i * (chip + gap)
        d.rounded_rectangle([x, dy - chip / 2, x + chip, dy + chip / 2], radius=12, fill=_CORAL)
        if lab:
            d.text((x + chip / 2, dy + 2), lab, font=chip_f, fill=_INK_PAPER, anchor="mm")
        else:
            d.line([(x + 20, dy), (x + chip - 22, dy)], fill=_INK_PAPER, width=7)
            d.polygon([(x + chip - 16, dy), (x + chip - 32, dy - 13), (x + chip - 32, dy + 13)], fill=_INK_PAPER)

    label_f = _font(_SORA, 30, "ExtraBold")
    for i, (lang, text) in enumerate(_examples(card, view, revealed=revealed)):
        y = 1345 + i * 66
        lw = label_f.getlength(f"{lang.upper()}:") + 18
        max_w = W - 2 * 90 - lw
        body_f = _fit(_SPECTRAL_IT, None, text, max_w, 46, floor=28)
        text = _trim(text, body_f, max_w)
        x = W / 2 - (lw + body_f.getlength(text)) / 2
        d.text((x, y), f"{lang.upper()}:", font=label_f, fill=_CORAL, anchor="lm")
        d.text((x + lw, y), text, font=body_f, fill=_INK_PAPER, anchor="lm")

    _spaced(d, W / 2, H - 46, f"{' '.join(SERVER_NAME)}  ·  {ANNIVERSARY}", _font(_SORA, 20, "Bold"),
            _FOOTER_GRAY, 5)
    return _export(_grain(img, 6), rounded=True)
