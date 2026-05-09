"""Round-end podium image for the Language League.

Renders a single celebratory PNG showing both leagues' final results:
a 2-1-3 Olympic podium for the top three of each league, plus a row
of compact cards for ranks 4-6. Intended to be sent alongside the
text announcement at the end of every round.

Reuses the low-level Pillow helpers from ``leaderboard_image_pillow``
(avatars, fonts, gradients) so the visual language stays consistent
with the existing leaderboard command.
"""
from __future__ import annotations

import logging
from io import BytesIO

from PIL import Image, ImageDraw

from .leaderboard_image_pillow import (
    create_default_avatar,
    download_avatar,
    draw_gradient_rect,
    get_font,
)

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Layout constants                                                            #
# --------------------------------------------------------------------------- #

WIDTH = 900
BANNER_H = 90
SECTION_H = 430     # per league
DIVIDER_H = 20
HEIGHT = BANNER_H + SECTION_H * 2 + DIVIDER_H   # = 970

# Palette — dark Discord-friendly background with bright accents.
BG = (26, 27, 30)
BANNER_TOP = (88, 101, 242)        # Discord blurple
BANNER_BOTTOM = (71, 82, 196)
TEXT_LIGHT = (255, 255, 255)
TEXT_MUTED = (185, 187, 190)
DIVIDER_COLOR = (46, 47, 53)

# Medal colors (top, bottom) for pedestal gradients.
MEDAL_COLORS: dict[int, tuple[tuple[int, int, int], tuple[int, int, int]]] = {
    1: ((255, 215, 0),   (212, 175, 55)),    # gold
    2: ((232, 232, 232), (176, 176, 176)),   # silver
    3: ((244, 164, 96),  (184, 115, 51)),    # bronze
}
MEDAL_EMOJI = {1: "#1", 2: "#2", 3: "#3"}

# Podium column centers (x) and heights (pixel offsets from baseline).
PODIUM_LAYOUT: dict[int, tuple[int, int]] = {
    # rank -> (x_center, pedestal_height)
    2: (225, 120),
    1: (450, 165),
    3: (675, 90),
}
PEDESTAL_WIDTH = 190
PODIUM_BASELINE_FROM_SECTION_TOP = 335   # where pedestal bottoms sit

# Avatars
AVATAR_TOP = 110       # bigger for 1st
AVATAR_OTHER = 92
AVATAR_RUNNER = 48     # small avatars for 4-6 cards

# Runner-up cards (ranks 4-6)
RUNNER_Y_FROM_SECTION_TOP = 350
RUNNER_H = 70
RUNNER_MARGIN_X = 18
RUNNER_CARD_COLOR_TOP = (88, 101, 191)
RUNNER_CARD_COLOR_BOTTOM = (61, 72, 155)


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #

def _load_avatar(url: str | None, size: int) -> Image.Image:
    """Best-effort avatar fetch with a default-avatar fallback."""
    if not url:
        return create_default_avatar(size)
    try:
        return download_avatar(url, size)
    except Exception:
        logger.debug("Avatar fetch failed for %s, using default", url)
        return create_default_avatar(size)


def _circular_border(avatar: Image.Image, border_px: int, color: tuple[int, int, int, int]) -> Image.Image:
    """Return a new image with a solid ring drawn around a circular avatar."""
    size = avatar.width
    out_size = size + border_px * 2
    out = Image.new("RGBA", (out_size, out_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(out)
    draw.ellipse((0, 0, out_size, out_size), fill=color)
    out.paste(avatar, (border_px, border_px), avatar)
    return out


def _fit_text(
    draw: ImageDraw.ImageDraw, text: str, font, max_width: int,
) -> str:
    """Truncate ``text`` with an ellipsis so it fits ``max_width``."""
    if draw.textlength(text, font=font) <= max_width:
        return text
    # Binary-ish shrink: chop one char at a time is fine for usernames.
    while text and draw.textlength(text + "…", font=font) > max_width:
        text = text[:-1]
    return (text + "…") if text else ""


def _draw_centered_text(
    draw: ImageDraw.ImageDraw,
    xy_center: tuple[int, int],
    text: str,
    font,
    fill: tuple[int, int, int],
) -> None:
    w = draw.textlength(text, font=font)
    bbox = draw.textbbox((0, 0), text, font=font)
    h = bbox[3] - bbox[1]
    draw.text((xy_center[0] - w / 2, xy_center[1] - h / 2), text, fill=fill, font=font)


# --------------------------------------------------------------------------- #
# Section renderers                                                           #
# --------------------------------------------------------------------------- #

def _render_banner(image: Image.Image, draw: ImageDraw.ImageDraw, round_number: int) -> None:
    """Top banner across the whole image."""
    # Gradient fill
    banner = Image.new("RGB", (WIDTH, BANNER_H), BG)
    banner_draw = ImageDraw.Draw(banner)
    draw_gradient_rect(banner_draw, (0, 0, WIDTH, BANNER_H), BANNER_TOP, BANNER_BOTTOM)
    image.paste(banner, (0, 0))

    title_font = get_font(38, bold=True)
    sub_font = get_font(18, bold=False)

    title = f"🏆  Round {round_number} — Final Results  🏆"
    _draw_centered_text(draw, (WIDTH // 2, BANNER_H // 2 - 8), title, title_font, TEXT_LIGHT)
    _draw_centered_text(
        draw, (WIDTH // 2, BANNER_H // 2 + 22),
        "Language League · Hablemos", sub_font, TEXT_MUTED,
    )


def _render_podium_slot(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    entry: dict,
    *,
    rank: int,
    section_top: int,
) -> None:
    """Render one podium pedestal + avatar + name + score."""
    x_center, pedestal_h = PODIUM_LAYOUT[rank]
    baseline = section_top + PODIUM_BASELINE_FROM_SECTION_TOP

    # Pedestal rectangle (gradient filled).
    ped_x0 = x_center - PEDESTAL_WIDTH // 2
    ped_y0 = baseline - pedestal_h
    ped_y1 = baseline

    ped_img = Image.new("RGB", (PEDESTAL_WIDTH, pedestal_h), BG)
    ped_draw = ImageDraw.Draw(ped_img)
    top_color, bot_color = MEDAL_COLORS[rank]
    draw_gradient_rect(ped_draw, (0, 0, PEDESTAL_WIDTH, pedestal_h), top_color, bot_color)

    # Rounded-corner mask for the pedestal.
    mask = Image.new("L", (PEDESTAL_WIDTH, pedestal_h), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle(
        (0, 0, PEDESTAL_WIDTH, pedestal_h), radius=12, fill=255,
    )
    image.paste(ped_img, (ped_x0, ped_y0), mask)

    # Rank label at the top of the pedestal.
    rank_font = get_font(28, bold=True)
    _draw_centered_text(
        draw, (x_center, ped_y0 + 22), MEDAL_EMOJI[rank], rank_font, (30, 30, 30),
    )

    # Username + score inside the pedestal.
    name_font = get_font(18, bold=True)
    score_font = get_font(16, bold=False)

    if entry is None:
        _draw_centered_text(
            draw, (x_center, (ped_y0 + ped_y1) // 2 + 10),
            "—", name_font, (50, 50, 50),
        )
    else:
        name = _fit_text(
            draw, entry["username"], name_font, PEDESTAL_WIDTH - 20,
        )
        _draw_centered_text(
            draw, (x_center, ped_y1 - 40), name, name_font, (30, 30, 30),
        )
        _draw_centered_text(
            draw, (x_center, ped_y1 - 18),
            f"{entry['total_score']} pts", score_font, (60, 60, 60),
        )

    # Avatar above the pedestal.
    avatar_size = AVATAR_TOP if rank == 1 else AVATAR_OTHER
    if entry is None:
        avatar = create_default_avatar(avatar_size)
        border_rgba: tuple[int, int, int, int] = (80, 80, 80, 255)
    else:
        avatar = _load_avatar(entry.get("avatar_url"), avatar_size)
        # Winners get a bold colored ring matching their medal.
        medal_top = MEDAL_COLORS[rank][0]
        border_rgba = (*medal_top, 255)

    bordered = _circular_border(avatar, border_px=4, color=border_rgba)
    ax = x_center - bordered.width // 2
    ay = ped_y0 - bordered.height + 8   # slightly overlap the pedestal top
    image.paste(bordered, (ax, ay), bordered)

    # Gold-crown accent for 1st place.
    if rank == 1 and entry is not None:
        crown_font = get_font(30, bold=False)
        _draw_centered_text(
            draw, (x_center, ay - 18), "👑", crown_font, (255, 215, 0),
        )


def _render_runner_card(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    entry: dict | None,
    *,
    rank: int,
    slot_index: int,
    section_top: int,
) -> None:
    """One of the three runner-up (ranks 4-6) cards at the bottom of a section."""
    usable_width = WIDTH - 2 * RUNNER_MARGIN_X
    card_w = (usable_width - 2 * 12) // 3   # 12 px gap between cards
    card_x0 = RUNNER_MARGIN_X + slot_index * (card_w + 12)
    card_y0 = section_top + RUNNER_Y_FROM_SECTION_TOP
    card_x1 = card_x0 + card_w

    # Gradient background with rounded corners.
    card_img = Image.new("RGB", (card_w, RUNNER_H), BG)
    card_draw = ImageDraw.Draw(card_img)
    draw_gradient_rect(
        card_draw, (0, 0, card_w, RUNNER_H),
        RUNNER_CARD_COLOR_TOP, RUNNER_CARD_COLOR_BOTTOM,
    )
    mask = Image.new("L", (card_w, RUNNER_H), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle((0, 0, card_w, RUNNER_H), radius=10, fill=255)
    image.paste(card_img, (card_x0, card_y0), mask)

    rank_font = get_font(20, bold=True)
    name_font = get_font(16, bold=True)
    score_font = get_font(14, bold=False)

    # Rank label.
    draw.text(
        (card_x0 + 14, card_y0 + (RUNNER_H - 26) // 2),
        f"#{rank}", fill=TEXT_LIGHT, font=rank_font,
    )

    if entry is None:
        draw.text(
            (card_x0 + 60, card_y0 + RUNNER_H // 2 - 10),
            "— no entry —", fill=TEXT_MUTED, font=name_font,
        )
        return

    # Avatar.
    avatar = _load_avatar(entry.get("avatar_url"), AVATAR_RUNNER)
    ax = card_x0 + 56
    ay = card_y0 + (RUNNER_H - AVATAR_RUNNER) // 2
    image.paste(avatar, (ax, ay), avatar)

    # Name + score stacked to the right of the avatar.
    text_x = ax + AVATAR_RUNNER + 10
    max_text_width = card_x1 - text_x - 10
    name_text = _fit_text(draw, entry["username"], name_font, max_text_width)
    draw.text((text_x, card_y0 + 12), name_text, fill=TEXT_LIGHT, font=name_font)
    draw.text(
        (text_x, card_y0 + 36),
        f"{entry['total_score']} pts",
        fill=TEXT_MUTED, font=score_font,
    )


def _render_section(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    *,
    league_label: str,
    flag: str,
    entries: list[dict],
    section_top: int,
) -> None:
    """Render one league's header + podium + runners-up."""
    # Header.
    header_font = get_font(26, bold=True)
    draw.text(
        (RUNNER_MARGIN_X, section_top + 14),
        f"{flag}  {league_label}",
        fill=TEXT_LIGHT, font=header_font,
    )
    # Thin underline for the section header.
    draw.line(
        [
            (RUNNER_MARGIN_X, section_top + 52),
            (WIDTH - RUNNER_MARGIN_X, section_top + 52),
        ],
        fill=DIVIDER_COLOR, width=1,
    )

    # Index entries by rank for easy lookup.
    by_rank: dict[int, dict] = {int(e["rank"]): e for e in entries if "rank" in e}

    # Podium (ranks 1-3). Draw 2, then 1, then 3 so the tallest pedestal
    # sits centered and visually dominant.
    for rank in (2, 1, 3):
        _render_podium_slot(
            image, draw, by_rank.get(rank),
            rank=rank, section_top=section_top,
        )

    # Runners-up (ranks 4-6).
    for slot_index, rank in enumerate((4, 5, 6)):
        _render_runner_card(
            image, draw, by_rank.get(rank),
            rank=rank, slot_index=slot_index, section_top=section_top,
        )


# --------------------------------------------------------------------------- #
# Public API                                                                  #
# --------------------------------------------------------------------------- #

def render_round_end(
    *,
    round_number: int,
    spanish_top: list[dict],
    english_top: list[dict],
) -> BytesIO:
    """Render the round-end podium image for both leagues.

    Args:
        round_number: Just-finished round number (used in the banner).
        spanish_top: Up to six entries, each with ``rank`` (1-6),
            ``username``, ``total_score``, and optionally ``avatar_url``
            and ``is_previous_winner``. Missing ranks render as empty
            podium / runner slots.
        english_top: Same shape as ``spanish_top`` for the English league.

    Returns:
        A ``BytesIO`` positioned at 0, ready for ``discord.File``.
    """
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)

    # Banner.
    _render_banner(image, draw, round_number)

    # Spanish section.
    _render_section(
        image, draw,
        league_label="Spanish League",
        flag="🇪🇸",
        entries=spanish_top,
        section_top=BANNER_H,
    )

    # Divider between leagues.
    div_y = BANNER_H + SECTION_H
    draw.rectangle(
        [(0, div_y), (WIDTH, div_y + DIVIDER_H)],
        fill=DIVIDER_COLOR,
    )

    # English section.
    _render_section(
        image, draw,
        league_label="English League",
        flag="🇬🇧",
        entries=english_top,
        section_top=BANNER_H + SECTION_H + DIVIDER_H,
    )

    buf = BytesIO()
    image.save(buf, "PNG", optimize=True)
    buf.seek(0)
    return buf
