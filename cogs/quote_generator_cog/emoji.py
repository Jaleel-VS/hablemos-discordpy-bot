"""Emoji-to-image conversion for quote rendering."""
import re

# Twemoji CDN base — serves PNG images by Unicode codepoint
_TWEMOJI_BASE = "https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72"
_IMG_PX = 24

# Discord custom emoji: <:name:id> or <a:name:id>
_CUSTOM_EMOJI_RE = re.compile(r"<a?:([A-Za-z0-9_]+):([0-9]+)>")

# Broad Unicode emoji pattern — covers most common emoji ranges
_UNICODE_EMOJI_RE = re.compile(
    "["
    "\U0001f600-\U0001f64f"  # emoticons
    "\U0001f300-\U0001f5ff"  # symbols & pictographs
    "\U0001f680-\U0001f6ff"  # transport & map
    "\U0001f1e0-\U0001f1ff"  # flags
    "\U0001f900-\U0001f9ff"  # supplemental symbols
    "\U0001fa00-\U0001fa6f"  # chess, extended-A
    "\U0001fa70-\U0001faff"  # extended-A continued
    "\U00002702-\U000027b0"  # dingbats
    "\U0000fe00-\U0000fe0f"  # variation selectors
    "\U0000200d"             # ZWJ
    "\U000023e9-\U000023f3"  # misc symbols
    "\U000025aa-\U000025fe"  # geometric shapes
    "\U00002600-\U000026ff"  # misc symbols
    "\U00002934-\U00002935"  # arrows
    "\U00003030\U0000303d"   # wavy dash, part alternation
    "]+",
)


def _custom_to_img(match: re.Match) -> str:
    """Convert a custom Discord emoji match to an <img> tag."""
    emoji_id = match.group(2)
    name = match.group(1)
    return (
        f'<img src="https://cdn.discordapp.com/emojis/{emoji_id}.png"'
        f' alt="{name}" width="{_IMG_PX}" height="{_IMG_PX}"'
        f' style="vertical-align:middle;display:inline">'
    )


def _unicode_to_img(match: re.Match) -> str:
    """Convert a Unicode emoji match to a Twemoji <img> tag."""
    emoji = match.group(0)
    # Build codepoint string: strip variation selectors, join with -
    codepoints = "-".join(f"{ord(c):x}" for c in emoji if c != "\ufe0f")
    return (
        f'<img src="{_TWEMOJI_BASE}/{codepoints}.png"'
        f' alt="{emoji}" width="{_IMG_PX}" height="{_IMG_PX}"'
        f' style="vertical-align:middle;display:inline">'
    )


def replace_emoji_with_images(text: str) -> str:
    """Replace both custom Discord and Unicode emoji with inline <img> tags."""
    text = _CUSTOM_EMOJI_RE.sub(_custom_to_img, text)
    return _UNICODE_EMOJI_RE.sub(_unicode_to_img, text)
