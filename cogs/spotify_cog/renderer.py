"""Render a Spotify now-playing card image."""
import contextlib
from io import BytesIO
from pathlib import Path

import aiohttp
from PIL import Image, ImageDraw, ImageFont

FONT_DIR = Path(__file__).resolve().parent
ROBOTO_FONT = FONT_DIR / "fonts" / "Roboto.ttf"
SPOTIFY_LOGO = Path(__file__).resolve().parent / "spotify_logo.png"

# Card dimensions — render at 3x for crisp text, then export at 2x.
#
# Why two scale factors:
#
# - SCALE (internal super-sampling): Pillow renders the whole card at
#   this multiple of the output size and LANCZOS-downscales before
#   saving. Smooths the anti-aliased edges. 3x is the sweet spot.
#
# - OUTPUT_SCALE (display resolution multiplier): the final PNG is
#   twice the CSS pixel size we want Discord to render it at. Discord
#   (and browsers on retina/HiDPI screens) then downscale the PNG on
#   the client side, which stays crisp. Exporting at the 1x CSS size
#   means Discord has to *upscale* on retina displays, which is what
#   makes text look jagged regardless of how cleanly we rendered it.
#
# When libraqm is installed on the deploy host, Pillow automatically
# switches its layout engine to RAQM (HarfBuzz) for proper kerning and
# sub-pixel positioning — no code change required.
SCALE = 3
OUTPUT_SCALE = 2
DISPLAY_WIDTH = 580   # CSS pixels we want it displayed at in Discord
DISPLAY_HEIGHT = 200
OUTPUT_WIDTH = DISPLAY_WIDTH * OUTPUT_SCALE
OUTPUT_HEIGHT = DISPLAY_HEIGHT * OUTPUT_SCALE
WIDTH = DISPLAY_WIDTH * SCALE * OUTPUT_SCALE
HEIGHT = DISPLAY_HEIGHT * SCALE * OUTPUT_SCALE
PADDING = 20 * SCALE * OUTPUT_SCALE
ART_SIZE = 160 * SCALE * OUTPUT_SCALE
CORNER_RADIUS = 16 * SCALE * OUTPUT_SCALE


def _font(size: int, weight: str = "Regular") -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Return a Roboto font at the requested size and weight.

    Uses the variable Roboto TTF shipped in ``cogs/spotify_cog/fonts/``
    and selects a named weight axis (Light / Regular / Medium /
    SemiBold / Bold, etc.). One file covers every weight we need, so
    we don't have to bundle separate ``Roboto-Light.ttf`` /
    ``Roboto-Medium.ttf`` statics.
    """
    pt = size * SCALE * OUTPUT_SCALE
    if ROBOTO_FONT.exists():
        font = ImageFont.truetype(str(ROBOTO_FONT), pt)
        with contextlib.suppress(OSError, ValueError):
            # ``set_variation_by_name`` raises if the weight isn't a
            # valid axis value. We swallow the error so a typo falls
            # through to the default (Regular) weight rather than
            # crashing the render.
            font.set_variation_by_name(weight)
        return font
    # Fallback to Helvetica if the Roboto file is missing (e.g. the
    # fonts directory wasn't copied into the container).
    fallback = FONT_DIR.parent / "league_cog" / "league_helper" / "fonts" / "HelveticaNeue-Roman.ttf"
    if fallback.exists():
        return ImageFont.truetype(str(fallback), pt)
    return ImageFont.load_default()


def _ensure_contrast(r: int, g: int, b: int) -> tuple[int, int, int]:
    """Adjust color to ensure white text is readable on it."""
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    if lum > 160:
        # Too bright for white text — darken
        factor = 0.5
        return int(r * factor), int(g * factor), int(b * factor)
    if lum < 50:
        # Too dark — blend toward a muted version so it's not just black
        # Boost the most dominant channel to create some color
        mx = max(r, g, b, 1)
        return int(r / mx * 90 + 20), int(g / mx * 90 + 20), int(b / mx * 90 + 20)
    return r, g, b


def _round_corners(img: Image.Image, radius: int) -> Image.Image:
    """Apply rounded corners using an alpha mask."""
    mask = Image.new("L", img.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([(0, 0), img.size], radius, fill=255)
    img.putalpha(mask)
    return img


def _truncate(
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
) -> str:
    """Truncate text with ellipsis if it exceeds max_width."""
    if font.getlength(text) <= max_width:
        return text
    while font.getlength(text + "…") > max_width and len(text) > 1:
        text = text[:-1]
    return text + "…"


async def _fetch_image(url: str) -> Image.Image | None:
    try:
        async with aiohttp.ClientSession() as session, session.get(url) as resp:
            if resp.status != 200:
                return None
            data = await resp.read()
        return Image.open(BytesIO(data)).convert("RGBA")
    except Exception:
        return None


async def render_nowplaying(
    title: str,
    artist: str,
    album: str,
    album_art_url: str | None,
    accent: tuple[int, int, int] = (30, 215, 96),
    listener: str = "Someone",
) -> BytesIO:
    """Render a Spotify-style now-playing card. Returns PNG BytesIO."""
    r, g, b = _ensure_contrast(*accent)

    # Create card at 2x resolution for crisp text
    card = Image.new("RGBA", (WIDTH, HEIGHT), (r, g, b, 255))
    draw = ImageDraw.Draw(card)

    # Album art
    art_x, art_y = PADDING, PADDING
    if album_art_url:
        art = await _fetch_image(album_art_url)
        if art:
            art = art.resize((ART_SIZE, ART_SIZE), Image.Resampling.LANCZOS)
            art = _round_corners(art, 8 * SCALE)
            card.paste(art, (art_x, art_y), art)

    # Text area
    text_x = art_x + ART_SIZE + PADDING
    text_max_w = WIDTH - text_x - PADDING

    title_font = _font(22, "SemiBold")
    artist_font = _font(15, "Regular")
    album_font = _font(13, "Light")
    label_font = _font(11, "Light")

    title_text = _truncate(title, title_font, text_max_w)
    artist_text = _truncate(artist, artist_font, text_max_w)
    album_text = _truncate(album, album_font, text_max_w)

    # Spotify logo (top-right)
    if SPOTIFY_LOGO.exists():
        logo = Image.open(SPOTIFY_LOGO).convert("RGBA")
        logo_size = 28 * SCALE * OUTPUT_SCALE
        logo = logo.resize((logo_size, logo_size), Image.Resampling.LANCZOS)
        card.paste(logo, (WIDTH - PADDING - logo_size, PADDING), logo)

    # Draw text.
    #
    # ``anchor="la"`` means "left edge, ascender line" — the y-coordinate
    # we pass is the top of the tallest glyph, independent of the font's
    # internal baseline quirks. This gives consistent vertical spacing
    # across fonts/weights and avoids the 1-2 px jitter that Pillow's
    # default ("la" is not the default) can produce between lines.
    white = (255, 255, 255)
    white_dim = (255, 255, 255, 180)

    text_y = PADDING + 16 * SCALE * OUTPUT_SCALE
    draw.text(
        (text_x, text_y),
        f"{listener} is listening to",
        fill=white_dim, font=label_font, anchor="la",
    )

    text_y += 28 * SCALE * OUTPUT_SCALE
    draw.text(
        (text_x, text_y),
        title_text,
        fill=white, font=title_font, anchor="la",
    )

    text_y += 36 * SCALE * OUTPUT_SCALE
    draw.text(
        (text_x, text_y),
        artist_text,
        fill=white, font=artist_font, anchor="la",
    )

    text_y += 26 * SCALE * OUTPUT_SCALE
    draw.text(
        (text_x, text_y),
        album_text,
        fill=white_dim, font=album_font, anchor="la",
    )

    # Round corners
    card = _round_corners(card, CORNER_RADIUS)

    # Flatten onto accent-colored background so the rounded corners
    # blend cleanly into the surrounding accent instead of fringing.
    flat = Image.new("RGBA", card.size, (r, g, b, 255))
    flat.paste(card, mask=card.split()[3])

    # Downscale from the super-sampled working canvas to the 2x output
    # size. We intentionally do *not* downscale all the way to the 1x
    # display size — exporting at 2x keeps the PNG sharp when Discord
    # renders it on a retina/HiDPI client, where a 1x PNG would get
    # upscaled by the browser and look blurry.
    flat = flat.resize(
        (OUTPUT_WIDTH, OUTPUT_HEIGHT),
        Image.Resampling.LANCZOS,
    )

    buf = BytesIO()
    flat.save(buf, "PNG")
    buf.seek(0)
    return buf
