"""Generate an aggressive tomato-throwing GIF animation.

Lightweight Pillow-only generator — no external overlay assets.
Produces a GIF with:
  1. Rapid-fire tomatoes flying at the avatar from all angles
  2. Splat impacts accumulating on the face
  3. Final smear frame covering everything in red
"""
from __future__ import annotations

import math
import random
from io import BytesIO

from PIL import Image, ImageDraw, ImageFilter

# Output size
SIZE = 256
# Animation params
THROW_FRAMES = 18       # Frames of tomatoes flying in
SPLAT_FRAMES = 6        # Frames of splat accumulating
SMEAR_FRAMES = 4        # Final smear/drip frames
TOTAL_FRAMES = THROW_FRAMES + SPLAT_FRAMES + SMEAR_FRAMES
FRAME_DURATION_MS = 60  # Fast and aggressive


def _draw_tomato(draw: ImageDraw.ImageDraw, x: int, y: int, radius: int) -> None:
    """Draw a simple tomato (red circle with green stem)."""
    # Body
    draw.ellipse(
        [(x - radius, y - radius), (x + radius, y + radius)],
        fill=(220, 30, 20),
        outline=(180, 20, 10),
        width=max(1, radius // 8),
    )
    # Highlight
    hr = radius // 3
    draw.ellipse(
        [(x - hr, y - radius + hr // 2), (x + hr // 2, y - radius + hr + hr // 2)],
        fill=(255, 80, 60),
    )
    # Stem
    stem_w = max(2, radius // 5)
    draw.rectangle(
        [(x - stem_w, y - radius - stem_w * 2), (x + stem_w, y - radius + stem_w)],
        fill=(40, 140, 30),
    )


def _draw_splat(draw: ImageDraw.ImageDraw, x: int, y: int, size: int) -> None:
    """Draw a tomato splat mark."""
    # Main splat blob
    draw.ellipse(
        [(x - size, y - size // 2), (x + size, y + size // 2)],
        fill=(200, 30, 20, 200),
    )
    # Splash droplets
    rng = random.Random(x * 1000 + y)
    for _ in range(5):
        dx = rng.randint(-size, size)
        dy = rng.randint(-size, size)
        dr = rng.randint(2, size // 3)
        draw.ellipse(
            [(x + dx - dr, y + dy - dr), (x + dx + dr, y + dy + dr)],
            fill=(220, 40, 30, 180),
        )


def generate_tomatoes(avatar: Image.Image) -> BytesIO:
    """Generate an aggressive tomato-throwing GIF.

    Parameters
    ----------
    avatar: RGBA PIL Image (will be resized to 256x256)

    Returns
    -------
    BytesIO with the GIF data, seeked to 0.
    """
    avatar = avatar.resize((SIZE, SIZE), Image.Resampling.LANCZOS).convert("RGBA")
    frames: list[Image.Image] = []

    # Pre-generate tomato trajectories (more = more aggressive)
    rng = random.Random(42)
    num_tomatoes = 12
    trajectories: list[dict] = []
    for _ in range(num_tomatoes):
        # Start from random edge
        angle = rng.uniform(0, 2 * math.pi)
        start_dist = SIZE * 0.8
        sx = SIZE // 2 + int(math.cos(angle) * start_dist)
        sy = SIZE // 2 + int(math.sin(angle) * start_dist)
        # Target near center with some spread
        tx = SIZE // 2 + rng.randint(-40, 40)
        ty = SIZE // 2 + rng.randint(-40, 40)
        # Start frame (stagger the throws)
        start_frame = rng.randint(0, THROW_FRAMES - 5)
        radius = rng.randint(14, 24)
        trajectories.append({
            "sx": sx, "sy": sy, "tx": tx, "ty": ty,
            "start": start_frame, "radius": radius,
        })

    # Track accumulated splats
    splat_layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))

    # -- Phase 1: Tomatoes flying in --
    for frame_i in range(THROW_FRAMES):
        img = avatar.copy()
        # Draw accumulated splats so far
        img = Image.alpha_composite(img, splat_layer)
        overlay = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)

        for t in trajectories:
            if frame_i < t["start"]:
                continue
            progress = (frame_i - t["start"]) / max(1, (THROW_FRAMES - t["start"] - 2))
            progress = min(1.0, progress)

            if progress >= 1.0:
                # Hit! Add to splat layer
                sd = ImageDraw.Draw(splat_layer)
                _draw_splat(sd, t["tx"], t["ty"], t["radius"])
            else:
                # In flight
                ease = progress * progress  # accelerate
                x = int(t["sx"] + (t["tx"] - t["sx"]) * ease)
                y = int(t["sy"] + (t["ty"] - t["sy"]) * ease)
                _draw_tomato(od, x, y, t["radius"])

        img = Image.alpha_composite(img, overlay)
        frames.append(img.convert("RGBA"))

    # -- Phase 2: Splats intensify --
    for _frame_i in range(SPLAT_FRAMES):
        img = avatar.copy()
        # Add more splats
        sd = ImageDraw.Draw(splat_layer)
        for _ in range(4):
            x = rng.randint(20, SIZE - 20)
            y = rng.randint(20, SIZE - 20)
            _draw_splat(sd, x, y, rng.randint(15, 30))

        img = Image.alpha_composite(img, splat_layer)
        frames.append(img.convert("RGBA"))

    # -- Phase 3: Final smear --
    for frame_i in range(SMEAR_FRAMES):
        img = avatar.copy()
        img = Image.alpha_composite(img, splat_layer)

        # Progressive red smear overlay
        smear_alpha = int(100 + (frame_i / SMEAR_FRAMES) * 140)
        smear = Image.new("RGBA", (SIZE, SIZE), (180, 20, 10, smear_alpha))
        # Drip effect — darker at top
        sd = ImageDraw.Draw(smear)
        for yy in range(SIZE):
            drip_alpha = int(smear_alpha * (0.5 + 0.5 * (yy / SIZE)))
            sd.line([(0, yy), (SIZE, yy)], fill=(160, 20, 10, drip_alpha))

        img = Image.alpha_composite(img, smear)

        # Blur slightly for a messy look
        img = img.filter(ImageFilter.GaussianBlur(radius=1 + frame_i))
        frames.append(img.convert("RGBA"))

    # Convert to GIF
    buf = BytesIO()
    gif_frames = [f.convert("P", palette=Image.Palette.ADAPTIVE, colors=128) for f in frames]
    gif_frames[0].save(
        buf,
        format="GIF",
        save_all=True,
        append_images=gif_frames[1:],
        duration=FRAME_DURATION_MS,
        loop=0,
        disposal=2,
    )
    buf.seek(0)
    return buf
