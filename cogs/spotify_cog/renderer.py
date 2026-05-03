"""Render a Spotify now-playing card image."""
from io import BytesIO
from pathlib import Path

import aiohttp
from PIL import Image, ImageDraw, ImageFont

FONT_DIR = Path(__file__).resolve().parent.parent / "league_cog" / "league_helper" / "fonts"
SPOTIFY_LOGO = Path(__file__).resolve().parent / "spotify_logo.png"

# Card dimensions
WIDTH = 580
HEIGHT = 200
PADDING = 20
ART_SIZE = 160
CORNER_RADIUS = 16


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = FONT_DIR / "HelveticaNeue-Roman.ttf"
    if path.exists():
        return ImageFont.truetype(str(path), size)
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

    # Create card with rounded corners
    card = Image.new("RGBA", (WIDTH, HEIGHT), (r, g, b, 255))
    draw = ImageDraw.Draw(card)

    # Gradient overlay — very subtle darkening on right edge only
    for x in range(WIDTH // 2, WIDTH):
        alpha = int(30 * ((x - WIDTH // 2) / (WIDTH // 2)))
        draw.line([(x, 0), (x, HEIGHT)], fill=(0, 0, 0, alpha))

    # Album art
    art_x, art_y = PADDING, PADDING
    if album_art_url:
        art = await _fetch_image(album_art_url)
        if art:
            art = art.resize((ART_SIZE, ART_SIZE), Image.LANCZOS)
            # Round the album art corners
            art = _round_corners(art, 8)
            card.paste(art, (art_x, art_y), art)

    # Text area
    text_x = art_x + ART_SIZE + PADDING
    text_max_w = WIDTH - text_x - PADDING

    title_font = _font(24)
    artist_font = _font(17)
    album_font = _font(14)

    title_text = _truncate(title, title_font, text_max_w)
    artist_text = _truncate(artist, artist_font, text_max_w)
    album_text = _truncate(album, album_font, text_max_w)

    # Spotify logo (top-right)
    if SPOTIFY_LOGO.exists():
        logo = Image.open(SPOTIFY_LOGO).convert("RGBA")
        logo = logo.resize((24, 24), Image.LANCZOS)
        card.paste(logo, (WIDTH - PADDING - 24, PADDING), logo)

    # Draw text — white on colored background
    white = (255, 255, 255)
    white_dim = (255, 255, 255, 180)

    # Vertically center the text block
    text_y = PADDING + 16
    draw.text((text_x, text_y), "♫ Now Playing", fill=white_dim, font=_font(12))

    text_y += 26
    draw.text((text_x, text_y), title_text, fill=white, font=title_font)

    text_y += 34
    draw.text((text_x, text_y), artist_text, fill=white, font=artist_font)

    text_y += 26
    draw.text((text_x, text_y), album_text, fill=white_dim, font=album_font)

    # Round the whole card
    card = _round_corners(card, CORNER_RADIUS)

    # Flatten to RGB for Discord (no transparency needed)
    flat = Image.new("RGB", card.size, (47, 49, 54))  # Discord dark bg
    flat.paste(card, mask=card.split()[3])

    buf = BytesIO()
    flat.save(buf, "PNG")
    buf.seek(0)
    return buf
