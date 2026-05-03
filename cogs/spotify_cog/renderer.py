"""Render a Spotify now-playing card image."""
from io import BytesIO
from pathlib import Path

import aiohttp
from PIL import Image, ImageDraw, ImageFont

FONT_DIR = Path(__file__).resolve().parent
SPOTIFY_LOGO = Path(__file__).resolve().parent / "spotify_logo.png"

# Card dimensions — render at 2x for crisp text, resize at end
SCALE = 2
WIDTH = 580 * SCALE
HEIGHT = 200 * SCALE
PADDING = 20 * SCALE
ART_SIZE = 160 * SCALE
CORNER_RADIUS = 16 * SCALE
OUTPUT_WIDTH = 580


def _font(size: int, weight: str = "Regular") -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = FONT_DIR / f"Poppins-{weight}.ttf"
    if path.exists():
        return ImageFont.truetype(str(path), size * SCALE)
    # Fallback to Helvetica
    fallback = FONT_DIR.parent / "league_cog" / "league_helper" / "fonts" / "HelveticaNeue-Roman.ttf"
    if fallback.exists():
        return ImageFont.truetype(str(fallback), size * SCALE)
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


def _truncate(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> str:
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
            art = art.resize((ART_SIZE, ART_SIZE), Image.LANCZOS)
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
        logo_size = 28 * SCALE
        logo = logo.resize((logo_size, logo_size), Image.LANCZOS)
        card.paste(logo, (WIDTH - PADDING - logo_size, PADDING), logo)

    # Draw text
    white = (255, 255, 255)
    white_dim = (255, 255, 255, 180)

    text_y = PADDING + 16 * SCALE
    draw.text((text_x, text_y), "Now Playing", fill=white_dim, font=label_font)

    text_y += 28 * SCALE
    draw.text((text_x, text_y), title_text, fill=white, font=title_font)

    text_y += 36 * SCALE
    draw.text((text_x, text_y), artist_text, fill=white, font=artist_font)

    text_y += 26 * SCALE
    draw.text((text_x, text_y), album_text, fill=white_dim, font=album_font)

    # Round corners
    card = _round_corners(card, CORNER_RADIUS)

    # Flatten onto accent-colored background (not Discord dark) so corners blend
    flat = Image.new("RGBA", card.size, (r, g, b, 255))
    flat.paste(card, mask=card.split()[3])

    # Downscale to output size with antialiasing
    flat = flat.resize((OUTPUT_WIDTH, OUTPUT_WIDTH * HEIGHT // WIDTH), Image.LANCZOS)

    buf = BytesIO()
    flat.save(buf, "PNG")
    buf.seek(0)
    return buf
