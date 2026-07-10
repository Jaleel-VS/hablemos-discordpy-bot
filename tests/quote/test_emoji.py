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
