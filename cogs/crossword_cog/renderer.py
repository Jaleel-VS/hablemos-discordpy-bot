"""Render a crossword grid as a PNG image using Pillow."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .grid import Grid

# Layout constants
CELL_SIZE = 56
CELL_GAP = 3
PADDING = 24
NUMBER_FONT_SIZE = 13
LETTER_FONT_SIZE = 26

# Colors (Discord dark-theme friendly)
BG_COLOR = (43, 45, 49)
CELL_BG = (255, 255, 255)
CELL_SOLVED = (87, 242, 135)
CELL_BORDER = (43, 45, 49)
LETTER_COLOR = (30, 31, 34)
NUMBER_COLOR = (120, 120, 120)
REVEALED_COLOR = (170, 170, 170)

FONT_DIR = Path(__file__).resolve().parent.parent / "league_cog" / "league_helper" / "fonts"


def _get_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load Helvetica or fall back to default."""
    font_path = FONT_DIR / "HelveticaNeue-Roman.ttf"
    if font_path.exists():
        return ImageFont.truetype(str(font_path), size)
    return ImageFont.load_default()


def render_grid(
    grid: Grid,
    solved_indices: set[int],
    revealed_cells: dict[tuple[int, int], str],
) -> BytesIO:
    """Render the crossword grid to a PNG BytesIO buffer.

    Args:
        grid: The crossword grid with placed words.
        solved_indices: Set of PlacedWord indices that have been solved.
        revealed_cells: Pre-revealed cells mapping (row, col) -> letter.
    """
    min_r, min_c, max_r, max_c = grid.bounds
    cols = max_c - min_c + 1
    rows = max_r - min_r + 1

    step = CELL_SIZE + CELL_GAP
    width = PADDING * 2 + cols * step - CELL_GAP
    height = PADDING * 2 + rows * step - CELL_GAP

    img = Image.new("RGB", (width, height), BG_COLOR)
    draw = ImageDraw.Draw(img)

    letter_font = _get_font(LETTER_FONT_SIZE)
    number_font = _get_font(NUMBER_FONT_SIZE)

    # Build set of solved cells
    solved_cells: set[tuple[int, int]] = set()
    for idx in solved_indices:
        for r, c in grid.placed[idx].cells:
            solved_cells.add((r, c))

    # Number positions: top-left of the first cell of each word
    number_positions: dict[tuple[int, int], int] = {}
    for pw in grid.placed:
        pos = (pw.row, pw.col)
        if pos not in number_positions:
            number_positions[pos] = pw.number

    # Draw cells
    for (r, c), letter in grid.cells.items():
        x = PADDING + (c - min_c) * step
        y = PADDING + (r - min_r) * step

        bg = CELL_SOLVED if (r, c) in solved_cells else CELL_BG

        # Rounded rectangle cell
        draw.rounded_rectangle(
            [x, y, x + CELL_SIZE, y + CELL_SIZE],
            radius=4, fill=bg, outline=CELL_BORDER, width=1,
        )

        # Draw number if this is a word start
        if (r, c) in number_positions:
            draw.text(
                (x + 4, y + 2),
                str(number_positions[(r, c)]),
                fill=NUMBER_COLOR, font=number_font,
            )

        # Draw letter if solved or revealed
        show_letter = None
        color = LETTER_COLOR

        if (r, c) in solved_cells:
            show_letter = letter.upper()
        elif (r, c) in revealed_cells:
            show_letter = revealed_cells[(r, c)].upper()
            color = REVEALED_COLOR

        if show_letter:
            bbox = draw.textbbox((0, 0), show_letter, font=letter_font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            lx = x + (CELL_SIZE - tw) // 2
            ly = y + (CELL_SIZE - th) // 2 + 2
            draw.text((lx, ly), show_letter, fill=color, font=letter_font)

    buf = BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    return buf
