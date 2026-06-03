"""Leaderboard image generation using Pillow.

Render at SCALE × OUTPUT_SCALE internally, then LANCZOS-downsample to
OUTPUT_SCALE before saving — same dual-scale approach as the Spotify
renderer.  The result is sharp on retina/HiDPI Discord clients without
any upscaling artifacts.
"""
import logging
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Scale constants
# SCALE        — internal super-sample multiplier; render everything at this
#                multiple of the output resolution, then LANCZOS-downsample.
# OUTPUT_SCALE — the output PNG is this many times the CSS display size.
#                Discord (and retina browsers) downscale on the client side,
#                keeping text crisp.  A 1x export would be upscaled on HiDPI
#                displays and look jagged regardless of render quality.
# S            — combined shorthand used for all internal pixel math.
# ---------------------------------------------------------------------------
SCALE = 3
OUTPUT_SCALE = 2
S = SCALE * OUTPUT_SCALE  # 6

DISPLAY_WIDTH = 800       # CSS pixels Discord displays the image at
DISPLAY_ENTRY_HEIGHT = 80
DISPLAY_PADDING = 20

FONT_DIR = Path(__file__).parent / "fonts"


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Return a HelveticaNeue font at the requested scaled size."""
    pt = size * S
    try:
        if bold:
            path = FONT_DIR / "HelveticaNeue-Bold.ttf"
            if not path.exists():
                path = FONT_DIR / "HelveticaNeue-Roman.ttf"
        else:
            path = FONT_DIR / "HelveticaNeue-Roman.ttf"
        if path.exists():
            return ImageFont.truetype(str(path), pt)
    except Exception:
        pass
    return ImageFont.load_default()


def _round_corners(img: Image.Image, radius: int) -> Image.Image:
    """Apply rounded corners via an alpha mask (in-place)."""
    mask = Image.new("L", img.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([(0, 0), img.size], radius, fill=255)
    img.putalpha(mask)
    return img


def _gradient_rect(
    draw: ImageDraw.ImageDraw,
    bbox: tuple[int, int, int, int],
    color1: tuple[int, int, int],
    color2: tuple[int, int, int],
) -> None:
    """Vertical gradient fill inside *bbox*."""
    x0, y0, x1, y1 = bbox
    height = y1 - y0
    for i in range(height):
        t = i / height
        r = int(color1[0] + (color2[0] - color1[0]) * t)
        g = int(color1[1] + (color2[1] - color1[1]) * t)
        b = int(color1[2] + (color2[2] - color1[2]) * t)
        draw.rectangle([(x0, y0 + i), (x1, y0 + i + 1)], fill=(r, g, b))


def _download_avatar(url: str, size: int) -> Image.Image:
    """Fetch an avatar URL and return a circular RGBA image at *size* pixels."""
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        img = Image.open(BytesIO(resp.content)).convert("RGBA")
        img = img.resize((size, size), Image.Resampling.LANCZOS)
    except Exception:
        img = _default_avatar(size)

    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(img, (0, 0))
    out.putalpha(mask)
    return out


def _default_avatar(size: int) -> Image.Image:
    """Discord-blurple circle with a simple silhouette."""
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


def _rank_colors(rank: int) -> tuple[tuple, tuple]:
    if rank == 1:
        return (255, 215, 0), (255, 165, 0)
    if rank == 2:
        return (232, 232, 232), (192, 192, 192)
    if rank == 3:
        return (244, 164, 96), (205, 127, 50)
    if rank <= 10:
        return (88, 101, 191), (118, 75, 162)
    return (45, 105, 196), (37, 99, 235)


def _text_color(rank: int) -> tuple:
    return (0, 0, 0) if rank <= 3 else (255, 255, 255)


def generate_leaderboard_image(leaderboard_data: list[dict]) -> BytesIO:
    """Render leaderboard image. Returns a BytesIO PNG at OUTPUT_SCALE x display size.

    leaderboard_data entries must have keys:
        rank (int), user_id (int), username (str),
        total_score (int), active_days (int), avatar_url (str)
    """
    # Internal (super-sampled) dimensions
    WIDTH = DISPLAY_WIDTH * S
    ENTRY_HEIGHT = DISPLAY_ENTRY_HEIGHT * S
    PADDING = DISPLAY_PADDING * S
    HEIGHT = PADDING + len(leaderboard_data) * ENTRY_HEIGHT + PADDING

    image = Image.new("RGB", (WIDTH, HEIGHT), (26, 27, 30))
    draw = ImageDraw.Draw(image)

    rank_font = _font(28, bold=True)
    username_font = _font(24, bold=False)
    score_font = _font(20, bold=True)

    RANK_AREA = 60 * S
    AVATAR_SIZE = 56 * S
    AVATAR_BORDER = 3 * S
    ENTRY_RADIUS = 12 * S

    y = PADDING
    for entry in leaderboard_data:
        rank = entry["rank"]
        username = entry["username"]
        total_score = entry["total_score"]
        avatar_url = entry["avatar_url"]

        bg1, bg2 = _rank_colors(rank)
        text_color = _text_color(rank)

        entry_w = WIDTH - 2 * PADDING
        entry_h = ENTRY_HEIGHT - 10 * S

        # Gradient background with rounded corners
        gradient = Image.new("RGB", (entry_w, entry_h))
        _gradient_rect(ImageDraw.Draw(gradient), (0, 0, entry_w, entry_h), bg1, bg2)
        mask = Image.new("L", (entry_w, entry_h), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, entry_w, entry_h), ENTRY_RADIUS, fill=255)
        image.paste(gradient, (PADDING, y), mask)

        # Rank badge
        rank_text = f"#{rank}"
        rb = draw.textbbox((0, 0), rank_text, font=rank_font)
        rx = PADDING + 20 * S
        ry = y + entry_h // 2 - (rb[3] - rb[1]) // 2
        draw.text((rx, ry), rank_text, fill=text_color, font=rank_font, anchor="la")

        # Avatar
        ax = PADDING + 20 * S + RANK_AREA
        ay = y + entry_h // 2 - AVATAR_SIZE // 2
        avatar = _download_avatar(avatar_url, AVATAR_SIZE)

        # White halo border
        border_sz = AVATAR_SIZE + AVATAR_BORDER * 2
        border = Image.new("RGBA", (border_sz, border_sz), (255, 255, 255, 100))
        bm = Image.new("L", (border_sz, border_sz), 0)
        ImageDraw.Draw(bm).ellipse((0, 0, border_sz, border_sz), fill=255)
        border.putalpha(bm)
        image.paste(border, (ax - AVATAR_BORDER, ay - AVATAR_BORDER), border)
        image.paste(avatar, (ax, ay), avatar)

        # Username (truncated)
        ux = ax + AVATAR_SIZE + 20 * S
        ub = draw.textbbox((0, 0), username, font=username_font)
        uy = y + entry_h // 2 - (ub[3] - ub[1]) // 2
        max_w = (WIDTH - PADDING - 20 * S - ux) - 120 * S
        utext = username
        if draw.textlength(utext, font=username_font) > max_w:
            while draw.textlength(utext + "…", font=username_font) > max_w and len(utext) > 1:
                utext = utext[:-1]
            utext += "…"
        draw.text((ux, uy), utext, fill=text_color, font=username_font, anchor="la")

        # Score (right-aligned)
        score_text = f"{total_score} pts"
        sb = draw.textbbox((0, 0), score_text, font=score_font)
        sx = WIDTH - PADDING - (sb[2] - sb[0]) - 20 * S
        sy = y + entry_h // 2 - (sb[3] - sb[1]) // 2
        draw.text((sx, sy), score_text, fill=text_color, font=score_font, anchor="la")

        y += ENTRY_HEIGHT

    # LANCZOS-downsample to OUTPUT_SCALE x display size.
    # Exporting at 2x keeps the PNG crisp on HiDPI Discord clients --
    # a 1x export would be upscaled by the browser and look blurry.
    output_w = DISPLAY_WIDTH * OUTPUT_SCALE
    output_h = (DISPLAY_PADDING * 2 + len(leaderboard_data) * DISPLAY_ENTRY_HEIGHT) * OUTPUT_SCALE
    image = image.resize((output_w, output_h), Image.Resampling.LANCZOS)

    buf = BytesIO()
    image.save(buf, "PNG")
    buf.seek(0)
    return buf

# ---------------------------------------------------------------------------
# Public aliases — consumed by round_end_image.py
# ---------------------------------------------------------------------------
create_default_avatar = _default_avatar
download_avatar = _download_avatar
draw_gradient_rect = _gradient_rect
get_font = _font


if __name__ == "__main__":
    sample_data = [
        {"rank": 1, "user_id": 1, "username": "TopPlayer", "total_score": 500,
         "active_days": 14, "avatar_url": "https://cdn.discordapp.com/embed/avatars/0.png"},
        {"rank": 2, "user_id": 2, "username": "SecondPlace", "total_score": 450,
         "active_days": 12, "avatar_url": "https://cdn.discordapp.com/embed/avatars/1.png"},
        {"rank": 3, "user_id": 3, "username": "ThirdPlace", "total_score": 400,
         "active_days": 11, "avatar_url": "https://cdn.discordapp.com/embed/avatars/2.png"},
    ]
    buf = generate_leaderboard_image(sample_data)
    Path("/tmp/leaderboard_test.png").write_bytes(buf.read())
    logger.info("Wrote /tmp/leaderboard_test.png")
