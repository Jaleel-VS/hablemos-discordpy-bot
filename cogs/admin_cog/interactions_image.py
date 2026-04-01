"""Generate an image showing top interaction pairs for a channel."""
import logging
from pathlib import Path

from PIL import Image, ImageDraw

from cogs.league_cog.league_helper.leaderboard_image_pillow import (
    create_default_avatar,
    download_avatar,
    draw_gradient_rect,
    get_font,
    get_rank_colors,
    get_text_color,
)

logger = logging.getLogger(__name__)


def generate_interactions_image(
    pairs: list[dict],
    channel_name: str,
    duration_label: str,
) -> str:
    """Generate an image of top interaction pairs.

    Args:
        pairs: List of dicts with keys user_a_name, user_b_name,
               user_a_avatar, user_b_avatar, replies, mentions.
        channel_name: Channel name for the filename.
        duration_label: Human-readable duration (e.g. "7d", "12h").

    Returns:
        Path to the generated PNG file.
    """
    WIDTH = 800
    ENTRY_HEIGHT = 80
    PADDING = 20
    MIN_HEIGHT = 500
    HEIGHT = max(MIN_HEIGHT, PADDING + len(pairs) * ENTRY_HEIGHT + PADDING)

    image = Image.new("RGB", (WIDTH, HEIGHT), color=(26, 27, 30))
    draw = ImageDraw.Draw(image)

    name_font = get_font(20, bold=False)
    detail_font = get_font(16, bold=False)
    rank_font = get_font(28, bold=True)

    y = PADDING
    avatar_size = 40

    for i, pair in enumerate(pairs, 1):
        bg1, bg2 = get_rank_colors(i)
        text_color = get_text_color(i)

        entry_w = WIDTH - 2 * PADDING
        entry_h = ENTRY_HEIGHT - 10

        # Gradient background with rounded corners
        grad = Image.new("RGB", (entry_w, entry_h))
        grad_draw = ImageDraw.Draw(grad)
        draw_gradient_rect(grad_draw, (0, 0, entry_w, entry_h), bg1, bg2)

        mask = Image.new("L", (entry_w, entry_h), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            (0, 0, entry_w, entry_h), radius=12, fill=255
        )
        image.paste(grad, (PADDING, y), mask)

        cy = y + entry_h // 2  # vertical center of row

        # Rank number
        rank_text = str(i)
        rb = draw.textbbox((0, 0), rank_text, font=rank_font)
        draw.text(
            (PADDING + 20, cy - (rb[3] - rb[1]) // 2),
            rank_text,
            fill=text_color,
            font=rank_font,
        )

        # Avatars side by side with a small overlap
        ax = PADDING + 70
        for avatar_url in (pair["user_a_avatar"], pair["user_b_avatar"]):
            av = download_avatar(avatar_url, avatar_size) if avatar_url else create_default_avatar(avatar_size)
            image.paste(av, (ax, cy - avatar_size // 2), av)
            ax += avatar_size - 6  # slight overlap

        # Names
        name_x = PADDING + 70 + 2 * avatar_size - 6 + 14
        name_str = f"{pair['user_a_name']}  &  {pair['user_b_name']}"
        max_name_w = 360
        if draw.textlength(name_str, font=name_font) > max_name_w:
            while (
                draw.textlength(name_str + "…", font=name_font) > max_name_w
                and len(name_str) > 10
            ):
                name_str = name_str[:-1]
            name_str += "…"
        nb = draw.textbbox((0, 0), name_str, font=name_font)
        draw.text(
            (name_x, cy - (nb[3] - nb[1]) - 2),
            name_str,
            fill=text_color,
            font=name_font,
        )

        # Reply/mention detail line
        parts = []
        if pair["replies"]:
            r = pair["replies"]
            parts.append(f"{r} {'reply' if r == 1 else 'replies'}")
        if pair["mentions"]:
            m = pair["mentions"]
            parts.append(f"{m} {'mention' if m == 1 else 'mentions'}")
        detail = ", ".join(parts)
        draw.text(
            (name_x, cy + 2),
            detail,
            fill=(*text_color[:3], 180) if len(text_color) == 4 else text_color,
            font=detail_font,
        )

        y += ENTRY_HEIGHT

    output = Path(__file__).parent / f"interactions_{channel_name}_{duration_label}.png"
    image.save(output, "PNG", quality=95)
    return str(output)
