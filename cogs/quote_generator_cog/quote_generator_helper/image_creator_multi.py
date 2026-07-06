"""Multi-message conversation-style quote image generator (Pillow).

Renders a Discord-styled conversation card with Pillow instead of the
HTML/wkhtmltoimage pipeline the older imgkit renderers use. Follows the
same **super-sample then LANCZOS-downsample** scheme as the reference
renderers (``spotify_cog/renderer.py``, ``league_cog`` leaderboard):
everything is drawn at ``S`` times the display size, then resized down to
``OUTPUT_SCALE`` before saving so text stays crisp on HiDPI Discord
clients.
"""
import logging
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

from cogs.quote_generator_cog.emoji import (
    render_visual_length,
    tokenize_for_render,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Scale constants — see spotify_cog/renderer.py for the full rationale.
# SCALE        — internal super-sample multiplier.
# OUTPUT_SCALE — the output PNG is this many times the display size so
#                HiDPI clients downscale (crisp) rather than upscale (blurry).
# S            — combined shorthand used for all internal pixel math.
# ---------------------------------------------------------------------------
SCALE = 3
OUTPUT_SCALE = 2
S = SCALE * OUTPUT_SCALE  # 6

# All layout constants are in *display* pixels; multiply by S when drawing.
DISPLAY_WIDTH = 620
CARD_PAD_X = 16
CARD_PAD_Y = 16
ROW_GAP = 14
AVATAR_SIZE = 40
AVATAR_GAP = 12
NAME_GAP = 4          # gap between name line and first text line
LINE_SPACING = 4      # extra leading between wrapped text lines

# Discord dark-theme palette
BG_COLOR = (43, 45, 49)          # #2b2d31
NAME_COLOR = (242, 243, 245)     # #f2f3f5
TEXT_COLOR = (219, 222, 225)     # #dbdee1
DIVIDER_COLOR = (255, 255, 255, 15)

NAME_FONT_PX = 15
FONT_DIR = Path(__file__).resolve().parent / "fonts"
FALLBACK_FONT_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "league_cog" / "league_helper" / "fonts"
)


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Return a HelveticaNeue font at the requested display size, scaled by S.

    The bundled Helvetica Neue only ships a Roman weight; the bold name
    line falls back to Roman if no bold file is present.
    """
    pt = size * S
    candidates = []
    if bold:
        candidates.append(FONT_DIR / "HelveticaNeue-Bold.ttf")
        candidates.append(FALLBACK_FONT_DIR / "HelveticaNeue-Bold.ttf")
    candidates.append(FONT_DIR / "HelveticaNeue-Roman.ttf")
    candidates.append(FALLBACK_FONT_DIR / "HelveticaNeue-Roman.ttf")
    for path in candidates:
        if path.exists():
            try:
                return ImageFont.truetype(str(path), pt)
            except OSError:
                continue
    return ImageFont.load_default()


def _line_height(font: ImageFont.FreeTypeFont | ImageFont.ImageFont, fallback_px: int) -> int:
    """Ascent + descent for *font*, falling back to the requested pixel size.

    ``ImageFont.load_default()`` (the last-resort bitmap font) has no
    ``getmetrics``, so fall back to the nominal size in that case.
    """
    getmetrics = getattr(font, "getmetrics", None)
    if getmetrics is not None:
        ascent, descent = getmetrics()
        return ascent + descent
    return fallback_px


def _compute_font_size(total_length: int) -> int:
    """Body-text display size, shrinking as the conversation gets longer."""
    if total_length <= 100:
        return 22
    if total_length <= 200:
        return 19
    if total_length <= 350:
        return 16
    return 14


def _fetch_image(url: str) -> Image.Image | None:
    """Fetch a remote image as RGBA. Returns None on any failure."""
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        return Image.open(BytesIO(resp.content)).convert("RGBA")
    except Exception:
        logger.debug("Failed to fetch image %s", url, exc_info=True)
        return None


def _default_avatar(size: int) -> Image.Image:
    """Discord-blurple circle used when an avatar can't be fetched."""
    img = Image.new("RGBA", (size, size), (114, 137, 218, 255))
    draw = ImageDraw.Draw(img)
    hs = size // 3
    draw.ellipse(
        (size // 2 - hs // 2, size // 3 - hs // 2,
         size // 2 + hs // 2, size // 3 + hs // 2),
        fill=(255, 255, 255, 255),
    )
    bw, bh = int(size * 0.6), int(size * 0.4)
    draw.ellipse(
        (size // 2 - bw // 2, size - bh,
         size // 2 + bw // 2, size - bh + bh * 2),
        fill=(255, 255, 255, 255),
    )
    return img


def _circular_avatar(url: str, size: int) -> Image.Image:
    """Fetch *url* and return a circular RGBA avatar at *size* pixels."""
    img = _fetch_image(url)
    if img is None:
        img = _default_avatar(size)
    else:
        img = img.resize((size, size), Image.Resampling.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(img, (0, 0))
    out.putalpha(mask)
    return out


# Emoji PNGs are fetched once per URL per render — small conversations
# reuse the same custom emoji repeatedly.
def _emoji_image(url: str, cache: dict[str, Image.Image | None], size: int) -> Image.Image | None:
    if url not in cache:
        img = _fetch_image(url)
        cache[url] = img.resize((size, size), Image.Resampling.LANCZOS) if img else None
    return cache[url]


class _Segment:
    """A laid-out inline segment: a word/space run or an emoji image."""

    __slots__ = ("image", "kind", "text", "width")

    def __init__(self, kind: str, width: int, text: str = "", image: Image.Image | None = None):
        self.kind = kind      # "text" | "emoji"
        self.text = text
        self.image = image
        self.width = width


def _break_long_word(
    word: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
    measure: ImageDraw.ImageDraw,
) -> list[_Segment]:
    """Break a word too wide for one line into character-chunk segments."""
    segments: list[_Segment] = []
    chunk = ""
    for char in word:
        candidate = chunk + char
        if chunk and int(measure.textlength(candidate, font=font)) > max_width:
            segments.append(_Segment("text", int(measure.textlength(chunk, font=font)), text=chunk))
            chunk = char
        else:
            chunk = candidate
    if chunk:
        segments.append(_Segment("text", int(measure.textlength(chunk, font=font)), text=chunk))
    return segments


def _wrap_content(
    content: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
    emoji_px: int,
    emoji_cache: dict[str, Image.Image | None],
    measure: ImageDraw.ImageDraw,
) -> list[list[_Segment]]:
    """Lay out *content* into wrapped lines of segments.

    Splits text on whitespace (keeping it word-wrapped) and treats each
    emoji as an inline fixed-width box. Returns a list of lines, each a
    list of ``_Segment``.
    """
    # Normalize newlines/tabs to spaces (HTML renderers collapse whitespace too).
    content = content.replace("\r", " ").replace("\n", " ").replace("\t", " ")

    # Flatten tokens into atomic units: words, single spaces, and emoji.
    units: list[_Segment] = []
    for kind, value in tokenize_for_render(content):
        if kind == "emoji":
            img = _emoji_image(value, emoji_cache, emoji_px)
            units.append(_Segment("emoji", emoji_px, image=img))
            continue
        # Split text into words and spaces so wrapping happens on spaces.
        for i, word in enumerate(value.split(" ")):
            if i > 0:
                sp_w = int(measure.textlength(" ", font=font))
                units.append(_Segment("text", sp_w, text=" "))
            if not word:
                continue
            w = int(measure.textlength(word, font=font))
            if w <= max_width:
                units.append(_Segment("text", w, text=word))
            else:
                # A single word wider than the line — break it into
                # character chunks so it wraps instead of overflowing.
                units.extend(_break_long_word(word, font, max_width, measure))

    lines: list[list[_Segment]] = [[]]
    line_w = 0
    for unit in units:
        # Skip a leading space on a fresh line.
        if not lines[-1] and unit.kind == "text" and unit.text == " ":
            continue
        if line_w + unit.width > max_width and lines[-1]:
            lines.append([])
            line_w = 0
            if unit.kind == "text" and unit.text == " ":
                continue
        lines[-1].append(unit)
        line_w += unit.width
    return lines


def create_multi_image(
    messages: list[tuple[str, str, str]],
    *,
    output_path: str | None = None,
) -> str:
    """Generate a conversation-style quote image with Pillow.

    Parameters
    ----------
    messages:
        List of (username, avatar_url, content) tuples, oldest first.
    output_path:
        Optional output file path. Defaults to ``picture_multi.png`` next
        to this module.

    Returns the output file path.
    """
    total_length = sum(render_visual_length(c) for _, _, c in messages)
    body_px = _compute_font_size(total_length)

    name_font = _font(NAME_FONT_PX, bold=True)
    text_font = _font(body_px, bold=False)

    # Scaled layout metrics (internal super-sampled pixels).
    width = DISPLAY_WIDTH * S
    pad_x = CARD_PAD_X * S
    pad_y = CARD_PAD_Y * S
    row_gap = ROW_GAP * S
    avatar_sz = AVATAR_SIZE * S
    avatar_gap = AVATAR_GAP * S
    name_gap = NAME_GAP * S
    line_spacing = LINE_SPACING * S
    emoji_px = body_px * S

    text_x = pad_x + avatar_sz + avatar_gap
    text_max_w = width - text_x - pad_x

    # Line heights from font metrics.
    name_h = _line_height(name_font, NAME_FONT_PX * S)
    text_line_h = _line_height(text_font, body_px * S)

    # A scratch draw context for text measurement before we know the height.
    measure = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    emoji_cache: dict[str, Image.Image | None] = {}

    # Lay out every row first so we can compute the total height.
    laid_out: list[tuple[str, str, list[list[_Segment]], int]] = []
    for username, avatar_url, content in messages:
        lines = _wrap_content(
            content, text_font, text_max_w, emoji_px, emoji_cache, measure,
        )
        text_block_h = (
            len(lines) * text_line_h + max(0, len(lines) - 1) * line_spacing
        )
        row_h = max(avatar_sz, name_h + name_gap + text_block_h)
        laid_out.append((username, avatar_url, lines, row_h))

    total_h = pad_y * 2 + sum(h for *_, h in laid_out) + row_gap * max(0, len(laid_out) - 1)

    image = Image.new("RGB", (width, total_h), BG_COLOR)
    draw = ImageDraw.Draw(image, "RGBA")

    y = pad_y
    for idx, (username, avatar_url, lines, row_h) in enumerate(laid_out):
        # Divider above every row except the first.
        if idx > 0:
            divider_y = y - row_gap // 2
            draw.line(
                [(pad_x, divider_y), (width - pad_x, divider_y)],
                fill=DIVIDER_COLOR, width=max(1, S // 3),
            )

        # Avatar.
        avatar = _circular_avatar(avatar_url, avatar_sz)
        image.paste(avatar, (pad_x, y), avatar)

        # Name line.
        draw.text((text_x, y), username, fill=NAME_COLOR, font=name_font, anchor="la")

        # Text lines.
        ty = y + name_h + name_gap
        for line in lines:
            tx = text_x
            for seg in line:
                if seg.kind == "emoji":
                    if seg.image is not None:
                        # Vertically center the emoji on the text line.
                        ey = ty + (text_line_h - seg.width) // 2
                        image.paste(seg.image, (tx, ey), seg.image)
                    tx += seg.width
                else:
                    draw.text((tx, ty), seg.text, fill=TEXT_COLOR, font=text_font, anchor="la")
                    tx += seg.width
            ty += text_line_h + line_spacing

        y += row_h + row_gap

    # LANCZOS-downsample from the super-sampled canvas to the OUTPUT_SCALE
    # export size. Exporting at 2x (not 1x) keeps text crisp on HiDPI.
    output_w = DISPLAY_WIDTH * OUTPUT_SCALE
    output_h = max(1, round(total_h / SCALE))
    image = image.resize((output_w, output_h), Image.Resampling.LANCZOS)

    img_path = output_path or str(Path(__file__).resolve().parent / "picture_multi.png")
    image.save(img_path, "PNG")
    return img_path
