"""World Cup knockout bracket renderer — Ro16 to Final.

Draws a classic tournament bracket image with Pillow.
Shows resolved teams in white, placeholders in gray, with
connecting lines between rounds.

House convention: render at S multiplier, LANCZOS-downsample.
"""
from __future__ import annotations

import contextlib
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from cogs.wcpredict_cog.fixtures import (
    FIXTURE_BY_ID,
    Fixture,
    is_placeholder_team,
)

# Fonts — reuse from vocabcatch
FONT_DIR = Path(__file__).resolve().parent.parent / "vocabcatch_cog" / "fonts"

# Render scale
S = 2

# Output dimensions (logical px)
WIDTH = 1100
HEIGHT = 620

# Layout constants
CELL_W = 160       # width of a match cell
CELL_H = 40        # height of a match cell (2 teams stacked)
TEAM_H = 20        # height per team row
ROUND_GAP = 60     # horizontal gap between rounds
MARGIN_X = 30
MARGIN_Y = 40

# Colors
BG = (20, 24, 36)
CELL_BG = (35, 42, 58)
CELL_BORDER = (55, 65, 85)
TEXT_WHITE = (240, 240, 240)
TEXT_DIM = (110, 120, 140)
ACCENT = (52, 211, 153)       # green for resolved/winner
GOLD = (251, 191, 36)         # gold for final
LINE_COLOR = (70, 80, 100)
HEADER_COLOR = (148, 163, 184)


# Match IDs for Ro16 onward
RO16_IDS = list(range(89, 97))       # 89–96 (8 matches)
QF_IDS = list(range(97, 101))        # 97–100 (4 matches)
SF_IDS = [101, 102]                   # 2 matches
THIRD_ID = 103
FINAL_ID = 104

# Bracket feed: which matches feed into which
# Ro16 → QF mapping (by position in the bracket)
# QF 97 = W89 vs W90, QF 98 = W93 vs W94, QF 99 = W91 vs W92, QF 100 = W95 vs W96
# SF 101 = W97 vs W98, SF 102 = W99 vs W100
# Final 104 = W101 vs W102


@lru_cache(maxsize=16)
def _font(name: str, size: int, variation: str | None = None) -> ImageFont.FreeTypeFont:
    """Load a font at size * S."""
    path = FONT_DIR / name
    f = ImageFont.truetype(str(path), size * S)
    if variation:
        with contextlib.suppress(OSError):
            f.set_variation_by_name(variation)
    return f


def _short_team(name: str) -> str:
    """Shorten team names and placeholders for the bracket."""
    if not is_placeholder_team(name):
        # Abbreviate long country names
        abbrevs = {
            "Bosnia and Herzegovina": "Bosnia",
            "Côte d'Ivoire": "Ivory Coast",
            "South Korea": "S. Korea",
            "Saudi Arabia": "Saudi",
            "New Zealand": "NZ",
            "Cabo Verde": "Cabo Verde",
            "DR Congo": "DR Congo",
        }
        return abbrevs.get(name, name)
    # Shorten placeholders: "Winner Match 89" → "W89"
    if name.startswith("Winner Match "):
        return f"W{name[13:]}"
    if name.startswith("Loser Match "):
        return f"L{name[12:]}"
    if name.startswith("Winner "):
        return name[7:][:8]
    return name[:10]


def _draw_cell(
    draw: ImageDraw.ImageDraw,
    x: int, y: int,
    fixture: Fixture,
    *,
    is_final: bool = False,
) -> None:
    """Draw a single match cell at (x, y) with two team rows."""
    cw = CELL_W * S
    ch = CELL_H * S
    th = TEAM_H * S
    r = 4 * S

    border = GOLD if is_final else CELL_BORDER
    draw.rounded_rectangle(
        [(x, y), (x + cw, y + ch)],
        radius=r,
        fill=CELL_BG,
        outline=border,
        width=1 * S,
    )

    # Divider between teams
    div_y = y + th
    draw.line([(x + 4 * S, div_y), (x + cw - 4 * S, div_y)], fill=border, width=1)

    home = fixture["home"]
    away = fixture["away"]

    font = _font("Inter.ttf", 9)
    pad_x = 6 * S
    # Home team (top)
    home_color = TEXT_WHITE if not is_placeholder_team(home) else TEXT_DIM
    draw.text((x + pad_x, y + 3 * S), _short_team(home), font=font, fill=home_color)

    # Away team (bottom)
    away_color = TEXT_WHITE if not is_placeholder_team(away) else TEXT_DIM
    draw.text((x + pad_x, div_y + 3 * S), _short_team(away), font=font, fill=away_color)

    # Date in tiny text on the right
    date_font = _font("Inter.ttf", 7)
    date_str = fixture["date"][5:]  # "MM-DD"
    date_w = draw.textlength(date_str, font=date_font)
    draw.text(
        (x + cw - date_w - pad_x, y + ch - 10 * S),
        date_str,
        font=date_font,
        fill=TEXT_DIM,
    )


def _connect_cells(
    draw: ImageDraw.ImageDraw,
    x1: int, y1: int,  # right edge of left cell, vertical center
    x2: int, y2: int,  # left edge of right cell, vertical center
) -> None:
    """Draw bracket connector lines between two rounds."""
    mid_x = (x1 + x2) // 2
    lw = max(1, 1 * S)
    draw.line([(x1, y1), (mid_x, y1)], fill=LINE_COLOR, width=lw)
    draw.line([(mid_x, y1), (mid_x, y2)], fill=LINE_COLOR, width=lw)
    draw.line([(mid_x, y2), (x2, y2)], fill=LINE_COLOR, width=lw)


def render_bracket() -> BytesIO:
    """Render the Ro16-to-Final bracket as a PNG BytesIO."""
    w, h = WIDTH * S, HEIGHT * S
    img = Image.new("RGB", (w, h), BG)
    draw = ImageDraw.Draw(img)

    # Title
    title_font = _font("Sora.ttf", 14, "Bold")
    draw.text((MARGIN_X * S, 10 * S), "FIFA WORLD CUP 2026 — KNOCKOUT BRACKET", font=title_font, fill=HEADER_COLOR)

    # Round headers
    header_font = _font("Inter.ttf", 8)
    rounds = ["ROUND OF 16", "QUARTERFINALS", "SEMIFINALS", "FINAL"]
    round_x_starts: list[int] = []

    for i, label in enumerate(rounds):
        rx = MARGIN_X * S + i * (CELL_W + ROUND_GAP) * S
        round_x_starts.append(rx)
        draw.text((rx, MARGIN_Y * S - 14 * S), label, font=header_font, fill=HEADER_COLOR)

    # Position cells for each round
    # Ro16: 8 matches, evenly spaced vertically
    ro16_fixtures = [FIXTURE_BY_ID[mid] for mid in RO16_IDS]
    qf_fixtures = [FIXTURE_BY_ID[mid] for mid in QF_IDS]
    sf_fixtures = [FIXTURE_BY_ID[mid] for mid in SF_IDS]
    final_fixture = FIXTURE_BY_ID[FINAL_ID]

    cell_positions: dict[int, tuple[int, int]] = {}  # match_id → (x, y)

    # Ro16: 8 cells stacked
    ro16_x = round_x_starts[0]
    ro16_spacing = (h - MARGIN_Y * S * 2) // 8
    for i, fix in enumerate(ro16_fixtures):
        cy = MARGIN_Y * S + i * ro16_spacing
        cell_positions[fix["match_id"]] = (ro16_x, cy)
        _draw_cell(draw, ro16_x, cy, fix)

    # QF: 4 cells, centered between pairs of Ro16
    qf_x = round_x_starts[1]
    for i, fix in enumerate(qf_fixtures):
        # Center between the two feeder Ro16 matches
        feeder_top = cell_positions[RO16_IDS[i * 2]][1]
        feeder_bot = cell_positions[RO16_IDS[i * 2 + 1]][1]
        cy = (feeder_top + feeder_bot) // 2
        cell_positions[fix["match_id"]] = (qf_x, cy)
        _draw_cell(draw, qf_x, cy, fix)

    # SF: 2 cells, centered between pairs of QF
    sf_x = round_x_starts[2]
    for i, fix in enumerate(sf_fixtures):
        feeder_top = cell_positions[QF_IDS[i * 2]][1]
        feeder_bot = cell_positions[QF_IDS[i * 2 + 1]][1]
        cy = (feeder_top + feeder_bot) // 2
        cell_positions[fix["match_id"]] = (sf_x, cy)
        _draw_cell(draw, sf_x, cy, fix)

    # Final: centered between the two SF
    final_x = round_x_starts[3]
    sf_top = cell_positions[SF_IDS[0]][1]
    sf_bot = cell_positions[SF_IDS[1]][1]
    final_cy = (sf_top + sf_bot) // 2
    cell_positions[FINAL_ID] = (final_x, final_cy)
    _draw_cell(draw, final_x, final_cy, final_fixture, is_final=True)

    # Draw connecting lines
    cw = CELL_W * S
    ch = CELL_H * S

    # Ro16 → QF
    for i in range(4):
        top_id = RO16_IDS[i * 2]
        bot_id = RO16_IDS[i * 2 + 1]
        qf_id = QF_IDS[i]

        top_pos = cell_positions[top_id]
        bot_pos = cell_positions[bot_id]
        qf_pos = cell_positions[qf_id]

        _connect_cells(
            draw,
            top_pos[0] + cw, top_pos[1] + ch // 2,
            qf_pos[0], qf_pos[1] + ch // 4,
        )
        _connect_cells(
            draw,
            bot_pos[0] + cw, bot_pos[1] + ch // 2,
            qf_pos[0], qf_pos[1] + 3 * ch // 4,
        )

    # QF → SF
    for i in range(2):
        top_id = QF_IDS[i * 2]
        bot_id = QF_IDS[i * 2 + 1]
        sf_id = SF_IDS[i]

        top_pos = cell_positions[top_id]
        bot_pos = cell_positions[bot_id]
        sf_pos = cell_positions[sf_id]

        _connect_cells(
            draw,
            top_pos[0] + cw, top_pos[1] + ch // 2,
            sf_pos[0], sf_pos[1] + ch // 4,
        )
        _connect_cells(
            draw,
            bot_pos[0] + cw, bot_pos[1] + ch // 2,
            sf_pos[0], sf_pos[1] + 3 * ch // 4,
        )

    # SF → Final
    sf_top_pos = cell_positions[SF_IDS[0]]
    sf_bot_pos = cell_positions[SF_IDS[1]]
    final_pos = cell_positions[FINAL_ID]

    _connect_cells(
        draw,
        sf_top_pos[0] + cw, sf_top_pos[1] + ch // 2,
        final_pos[0], final_pos[1] + ch // 4,
    )
    _connect_cells(
        draw,
        sf_bot_pos[0] + cw, sf_bot_pos[1] + ch // 2,
        final_pos[0], final_pos[1] + 3 * ch // 4,
    )

    # 3rd place match — small note at bottom right
    third = FIXTURE_BY_ID[THIRD_ID]
    note_font = _font("Inter.ttf", 8)
    third_text = f"3rd Place: {_short_team(third['home'])} vs {_short_team(third['away'])} ({third['date'][5:]})"
    draw.text(
        (final_x, final_cy + ch + 20 * S),
        third_text,
        font=note_font,
        fill=TEXT_DIM,
    )

    # Downsample
    final_img = img.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)

    buf = BytesIO()
    final_img.save(buf, format="PNG")
    buf.seek(0)
    return buf
