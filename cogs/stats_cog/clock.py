"""Pillow renderer for the activity clock (radial hour-of-day histogram).

Draws a 24-wedge radial chart: one annular sector per local hour, ``00`` at
the top going clockwise (``06`` right, ``12`` bottom, ``18`` left). A wedge's
length and colour are both keyed to that hour's share of the user's busiest
hour, so the peak hour is the longest and darkest petal — the same read as a
classic activity clock.

Rendering follows the repo's super-sample-then-LANCZOS convention: everything
is drawn at ``S`` times the display size, then downsampled on save for crisp
edges on HiDPI Discord clients. Fonts are loaded at literal ``* S`` sizes
directly (not via a shared ``get_font`` helper) to avoid the double-scale
pitfall documented in docs/architecture.md.

CPU-bound; call via ``asyncio.to_thread``.
"""
from __future__ import annotations

import io
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ── Scale (see docs/architecture.md "Image rendering (Pillow)") ──
SCALE = 3
OUTPUT_SCALE = 2
S = SCALE * OUTPUT_SCALE  # 6

DISPLAY = 340  # CSS pixels Discord displays the square image at

# ── Geometry, in display units (multiplied by S at draw time) ──
_CENTER = DISPLAY / 2
_R_OUTER = 158       # petal tip at the busiest hour
_FACE_RADIUS = 46    # central clock face
_INNER = 60          # petals start here (gap between face and petals)
_RING_WIDTH = _R_OUTER - _INNER
_WEDGE_GAP_DEG = 1.4  # angular gap between adjacent petals
_MIN_STUB = 5         # min petal length for a nonzero-but-tiny hour

# ── Palette (light page, blue ramp; darkest = busiest) ──
_BG = (255, 255, 255)
_TRACK = (234, 237, 241)         # pale petals behind the data
_RAMP_LOW = (198, 219, 239)      # quietest active hour
_RAMP_HIGH = (8, 48, 107)        # busiest hour
_FACE = (255, 255, 255)
_FACE_BORDER = (208, 214, 221)
_TICK = (176, 184, 194)
_GLYPH = (88, 101, 242)          # Discord blurple clock hands
_LABEL = (120, 131, 145)
_LABEL_NOON = (136, 84, 208)     # 12 accented, echoing the reference

_FONT_PATH = (
    Path(__file__).resolve().parent.parent
    / "quote_generator_cog"
    / "quote_generator_helper"
    / "fonts"
    / "HelveticaNeue-Roman.ttf"
)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load the label font at a display size, scaled to the super-sampled canvas."""
    try:
        if _FONT_PATH.exists():
            return ImageFont.truetype(str(_FONT_PATH), size * S)
    except OSError:
        pass
    return ImageFont.load_default()


def _lerp(low: tuple[int, int, int], high: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    """Linear-interpolate between two RGB colours (t clamped to [0, 1])."""
    t = max(0.0, min(1.0, t))
    return tuple(int(low[i] + (high[i] - low[i]) * t) for i in range(3))  # type: ignore[return-value]


def _pil_angle(hour: float) -> float:
    """Map a clock hour (0-24) to a PIL angle (0°=east, clockwise).

    PIL measures angles clockwise from 3 o'clock. Placing ``00`` at the top
    means north (270° in that system) plus 15° per hour.
    """
    return 270.0 + hour * 15.0


def _bbox(center: float, radius: float) -> list[float]:
    """Square bounding box for a circle of *radius* about *center*."""
    return [center - radius, center - radius, center + radius, center + radius]


def _draw_text_centered(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    font,
    fill: tuple[int, int, int],
) -> None:
    """Draw *text* centred on *xy*."""
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    draw.text(
        (xy[0] - (right - left) / 2, xy[1] - (bottom - top) / 2 - top),
        text,
        font=font,
        fill=fill,
    )


def render_activity_clock(hours: list[int], utc_offset: int) -> io.BytesIO:
    """Render the 24-hour activity clock to a PNG buffer.

    ``hours`` is a length-24 list of message counts indexed by local hour.
    ``utc_offset`` is the whole-hour offset used only for the corner label.
    """
    px = DISPLAY * S
    center = _CENTER * S
    img = Image.new("RGB", (px, px), _BG)
    draw = ImageDraw.Draw(img)

    peak = max(hours) if hours else 0
    half = (15.0 - _WEDGE_GAP_DEG) / 2.0

    # 1) Pale track petals (full length, every hour) behind the data.
    for h in range(24):
        c = _pil_angle(h)
        draw.pieslice(
            _bbox(center, _R_OUTER * S),
            c - half,
            c + half,
            fill=_TRACK,
        )

    # 2) Data petals: length + colour keyed to share of the peak hour.
    if peak > 0:
        for h in range(24):
            count = hours[h]
            if count <= 0:
                continue
            t = count / peak
            radius = _INNER + max(_MIN_STUB, _RING_WIDTH * t)
            c = _pil_angle(h)
            draw.pieslice(
                _bbox(center, radius * S),
                c - half,
                c + half,
                fill=_lerp(_RAMP_LOW, _RAMP_HIGH, t),
            )

    # 3) Carve the centre hole so petals read as an annulus.
    draw.ellipse(_bbox(center, _INNER * S), fill=_BG)

    # 4) Clock face: disc, border, hour ticks.
    draw.ellipse(_bbox(center, _FACE_RADIUS * S), fill=_FACE, outline=_FACE_BORDER, width=max(1, S // 3))
    for h in range(12):
        ang = math.radians(h * 30.0 - 90.0)
        r_out = _FACE_RADIUS - 5
        r_in = _FACE_RADIUS - 10
        draw.line(
            [
                (center + r_out * S * math.cos(ang), center + r_out * S * math.sin(ang)),
                (center + r_in * S * math.cos(ang), center + r_in * S * math.sin(ang)),
            ],
            fill=_TICK,
            width=max(1, S // 3),
        )

    # 5) Static clock glyph (hands frozen at ~10:10, like the reference).
    _draw_hand(draw, center, angle_deg=-60.0, length=_FACE_RADIUS - 18, width=max(2, S // 2))
    _draw_hand(draw, center, angle_deg=20.0, length=_FACE_RADIUS - 12, width=max(2, S // 2))
    draw.ellipse(_bbox(center, 2.5 * S), fill=_GLYPH)

    # 6) Cardinal hour labels just outside the face.
    label_r = (_FACE_RADIUS + _INNER) / 2
    label_font = _font(12)
    for hour, text in ((0, "00"), (6, "06"), (12, "12"), (18, "18")):
        ang = math.radians(_pil_angle(hour))
        pos = (center + label_r * S * math.cos(ang), center + label_r * S * math.sin(ang))
        fill = _LABEL_NOON if hour == 12 else _LABEL
        _draw_text_centered(draw, pos, text, label_font, fill)

    # 7) Timezone caption along the bottom edge.
    sign = "+" if utc_offset >= 0 else "−"
    _draw_text_centered(
        draw,
        (center, (DISPLAY - 12) * S),
        f"UTC {sign}{abs(utc_offset)}",
        _font(11),
        _LABEL,
    )

    # Downsample S → OUTPUT_SCALE for crisp HiDPI output.
    out_px = DISPLAY * OUTPUT_SCALE
    img = img.resize((out_px, out_px), Image.Resampling.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def _draw_hand(
    draw: ImageDraw.ImageDraw,
    center: float,
    *,
    angle_deg: float,
    length: float,
    width: int,
) -> None:
    """Draw a clock hand from the face centre at *angle_deg* (0°=east, CCW-up)."""
    ang = math.radians(angle_deg)
    draw.line(
        [
            (center, center),
            (center + length * S * math.cos(ang), center + length * S * math.sin(ang)),
        ],
        fill=_GLYPH,
        width=width,
    )
