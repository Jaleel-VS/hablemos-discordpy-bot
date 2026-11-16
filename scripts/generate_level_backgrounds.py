"""Generate the Language League level-card backgrounds with Stable Image Core.

Usage:
    python scripts/generate_level_backgrounds.py            # every tier
    python scripts/generate_level_backgrounds.py tide gold  # just these tiers

Writes ``cogs/league_cog/league_helper/level_backgrounds/<tier>.jpg``, cropped
to the card's aspect ratio. Needs the ``ada`` credentials that ``_bedrock`` uses.
Fixed seeds keep reruns close to the committed images; change a tier's seed or
prompt to get a new one, then check the card with ``/league profile``.
"""
from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _bedrock import bedrock_auth, bedrock_image

from cogs.league_cog.league_helper.level_card_image import BACKGROUND_SIZE
from cogs.league_cog.levels import TIERS

_STYLE = (
    "soft blurred gradient mesh background, smooth glowing organic blobs, frosted glass feel, "
    "minimal abstract, calm, the left side is a smooth nearly flat gradient, wide banner"
)
_NEGATIVE = (
    "text, letters, words, numbers, watermark, logo, signature, people, person, faces, "
    "clutter, busy, sharp edges, lines, grid, neon, cyberpunk, frame, border, noise"
)

# tier name -> (palette prompt, extra negative prompt, seed)
_PROMPTS: dict[str, tuple[str, str, int]] = {
    "Dawn": ("pale peach, cream and blush pink, very light and airy", "", 5),
    "Mist": ("pastel mint green and sky blue, light", "", 5),
    "Lilac": ("lilac, lavender and soft pink, medium brightness", "", 5),
    "Tide": (
        "deep navy, midnight blue and dark teal with soft cyan glow, dark and moody",
        "pastel, light background",
        5,
    ),
    "Bloom": ("vivid magenta, violet and electric blue, rich and deep", "", 5),
    "Gold": ("radiant gold, amber, rose and iridescent pearl highlights on deep plum, luxurious", "", 5),
}


def _crop_to_card(png: bytes) -> Image.Image:
    """Scale to the card width and keep the vertical middle."""
    width, height = BACKGROUND_SIZE
    image = Image.open(io.BytesIO(png)).convert("RGB")
    scaled_height = round(image.height * width / image.width)
    image = image.resize((width, scaled_height), Image.Resampling.LANCZOS)
    top = (scaled_height - height) // 2
    return image.crop((0, top, width, top + height))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the level-card backgrounds.")
    parser.add_argument("tiers", nargs="*", help="tier names (default: all)")
    args = parser.parse_args()

    wanted = {name.lower() for name in args.tiers}
    tiers = [t for t in TIERS if not wanted or t.name.lower() in wanted]
    unknown = wanted - {t.name.lower() for t in TIERS}
    if unknown:
        parser.error(f"unknown tiers: {', '.join(sorted(unknown))}")

    bedrock_auth()
    for tier in tiers:
        palette, negative, seed = _PROMPTS[tier.name]
        png = bedrock_image(
            f"{palette}, {_STYLE}",
            negative_prompt=", ".join(filter(None, [_NEGATIVE, negative])),
            aspect_ratio="21:9",
            seed=seed,
        )
        tier.background.parent.mkdir(parents=True, exist_ok=True)
        _crop_to_card(png).save(tier.background, "JPEG", quality=90, optimize=True)
        print(f"{tier.name}: {tier.background}")


if __name__ == "__main__":
    main()
