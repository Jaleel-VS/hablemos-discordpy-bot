"""Tests for quote emoji-to-image conversion.

Regression coverage for the bug where two adjacent standalone emoji were
joined into a single Twemoji codepoint string (e.g. ``1f60d-1f48b.png``),
which 404s — that form is reserved for ZWJ sequences.
"""
import re

from cogs.quote_generator_cog.emoji import (
    replace_emoji_with_images,
    tokenize_for_render,
)

SMILING = "\U0001f60d"        # 😍
KISS = "\U0001f48b"           # 💋
FAMILY = "\U0001f468‍\U0001f469‍\U0001f467"  # 👨‍👩‍👧 (ZWJ sequence)
FLAG_ES = "\U0001f1ea\U0001f1f8"  # 🇪🇸 (regional-indicator pair)
THUMBS_UP_TONED = "\U0001f44d\U0001f3fd"  # 👍🏽 (base + skin-tone modifier)
KEYCAP_ONE = "1️⃣"             # digit '1' + FE0F + combining enclosing keycap
ENGLAND_FLAG = (               # 🏴󠁧󠁢󠁥󠁮󠁧󠁿 (black flag + tag sequence + cancel tag)
    "\U0001f3f4\U000e0067\U000e0062\U000e0065\U000e006e\U000e0067\U000e007f"
)


def _img_codepoints(html: str) -> list[str]:
    """Extract the Twemoji filename stems from every <img> in *html*."""
    return re.findall(r"/72x72/([0-9a-f-]+)\.png", html)


def test_single_emoji_renders_one_image():
    html = replace_emoji_with_images(f"this is a test {KISS}")
    assert _img_codepoints(html) == ["1f48b"]


def test_adjacent_standalone_emoji_split_into_separate_images():
    # The original bug: these were joined into "1f60d-1f48b" (a 404).
    html = replace_emoji_with_images(f"hey {SMILING}{KISS}")
    assert _img_codepoints(html) == ["1f60d", "1f48b"]


def test_zwj_sequence_stays_joined():
    # ZWJ sequences are a single Twemoji file (joiners kept) — do NOT split.
    html = replace_emoji_with_images(FAMILY)
    assert _img_codepoints(html) == ["1f468-200d-1f469-200d-1f467"]


def test_regional_indicator_pair_stays_joined():
    html = replace_emoji_with_images(FLAG_ES)
    assert _img_codepoints(html) == ["1f1ea-1f1f8"]


def test_tokenize_for_render_splits_adjacent_emoji():
    # The Pillow path already split correctly; guard it stays that way.
    tokens = tokenize_for_render(f"hi {SMILING}{KISS}")
    emoji_urls = [v for kind, v in tokens if kind == "emoji"]
    assert [u.rsplit("/", 1)[-1] for u in emoji_urls] == ["1f60d.png", "1f48b.png"]


def test_skin_tone_modifier_stays_attached_to_base():
    # Regression: the modifier was split into its own cluster, rendering a
    # plain thumbs-up next to a floating skin-tone swatch instead of the
    # correctly-toned emoji.
    html = replace_emoji_with_images(THUMBS_UP_TONED)
    assert _img_codepoints(html) == ["1f44d-1f3fd"]


def test_keycap_sequence_renders_as_one_image():
    # Regression: '1' + FE0F + U+20E3 wasn't matched by the emoji regex at
    # all (the base character isn't in any emoji range), so no image was
    # produced and the literal digit + invisible combiner leaked as text.
    html = replace_emoji_with_images(f"press {KEYCAP_ONE} to continue")
    assert _img_codepoints(html) == ["31-20e3"]


def test_tag_sequence_flag_stays_joined():
    # Regression: tag characters (flag subdivisions, e.g. England within the
    # UK) weren't recognized, so only the black-flag base rendered and the
    # subdivision was silently dropped.
    html = replace_emoji_with_images(ENGLAND_FLAG)
    assert _img_codepoints(html) == ["1f3f4-e0067-e0062-e0065-e006e-e0067-e007f"]
