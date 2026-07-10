"""Emoji-to-image conversion for quote rendering."""
import re

# Twemoji CDN base — serves PNG images by Unicode codepoint
_TWEMOJI_BASE = "https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72"
_IMG_PX = 24
_LARGE_IMG_PX = 96
_IMG_STYLE = "vertical-align:text-bottom;display:inline"

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
        f' style="{_IMG_STYLE}">'
    )


def _cluster_to_img(cluster: str) -> str:
    """Build a Twemoji <img> tag for a single emoji cluster."""
    # Build codepoint string: strip variation selectors, join with -
    codepoints = "-".join(f"{ord(c):x}" for c in cluster if c != "\ufe0f")
    return (
        f'<img src="{_TWEMOJI_BASE}/{codepoints}.png"'
        f' alt="{cluster}" width="{_IMG_PX}" height="{_IMG_PX}"'
        f' style="{_IMG_STYLE}">'
    )


def _unicode_to_img(match: re.Match) -> str:
    """Convert a run of Unicode emoji to one Twemoji <img> tag per cluster.

    A regex match may span several standalone emoji (e.g. ``\ud83d\ude0d\ud83d\udc8b``); each is a
    separate Twemoji file, so split the run into clusters and emit one image
    each. Joining them (``1f60d-1f48b``) would 404 \u2014 that form is reserved for
    ZWJ sequences.
    """
    return "".join(
        _cluster_to_img(cluster)
        for cluster in _split_emoji_clusters(match.group(0))
    )


_IMG_TAG_RE = re.compile(r"<img[^>]*>")


def visual_length(text: str) -> int:
    """Return the visual length of text, counting each <img> tag as 1 character."""
    return len(_IMG_TAG_RE.sub("X", text))


def replace_emoji_with_images(text: str) -> str:
    """Replace both custom Discord and Unicode emoji with inline <img> tags.

    If the entire message is a single emoji, the image is rendered larger.
    """
    text = _CUSTOM_EMOJI_RE.sub(_custom_to_img, text)
    text = _UNICODE_EMOJI_RE.sub(_unicode_to_img, text)
    # Enlarge if the entire message is a single emoji image
    if _IMG_TAG_RE.fullmatch(text.strip()):
        text = text.replace(
            f'width="{_IMG_PX}" height="{_IMG_PX}"',
            f'width="{_LARGE_IMG_PX}" height="{_LARGE_IMG_PX}"',
        )
    return text


# ---------------------------------------------------------------------------
# Token-based helpers for the Pillow renderer (quotem).
#
# The imgkit renderers above inline emoji as HTML <img> tags. The Pillow
# renderer can't parse HTML, so it needs the emoji as structured tokens: a
# text run or an emoji with a resolvable PNG URL it can fetch and paste.
# ---------------------------------------------------------------------------

# Matches a custom Discord emoji or a run of Unicode emoji, capturing which.
_EMOJI_SPLIT_RE = re.compile(
    rf"({_CUSTOM_EMOJI_RE.pattern}|{_UNICODE_EMOJI_RE.pattern})",
)


def _custom_emoji_url(match: re.Match) -> str:
    """PNG URL for a custom Discord emoji `<a?:name:id>` match."""
    return f"https://cdn.discordapp.com/emojis/{match.group(2)}.png"


def _unicode_emoji_url(emoji: str) -> str:
    """Twemoji PNG URL for a single Unicode emoji cluster."""
    codepoints = "-".join(f"{ord(c):x}" for c in emoji if c != "\ufe0f")
    return f"{_TWEMOJI_BASE}/{codepoints}.png"


def tokenize_for_render(text: str) -> list[tuple[str, str]]:
    """Split *text* into ``(kind, value)`` tokens for the Pillow renderer.

    ``kind`` is either ``"text"`` (``value`` is a literal substring) or
    ``"emoji"`` (``value`` is a PNG URL). Consecutive Unicode emoji are
    emitted as one token per cluster so each renders as its own image.
    """
    tokens: list[tuple[str, str]] = []
    pos = 0
    for match in _EMOJI_SPLIT_RE.finditer(text):
        if match.start() > pos:
            tokens.append(("text", text[pos:match.start()]))
        custom = _CUSTOM_EMOJI_RE.fullmatch(match.group(0))
        if custom is not None:
            tokens.append(("emoji", _custom_emoji_url(custom)))
        else:
            # A Unicode run may contain several standalone emoji; split on
            # ZWJ-joined clusters so each glyph gets its own Twemoji image.
            for cluster in _split_emoji_clusters(match.group(0)):
                tokens.append(("emoji", _unicode_emoji_url(cluster)))
        pos = match.end()
    if pos < len(text):
        tokens.append(("text", text[pos:]))
    return tokens


def _is_regional_indicator(char: str) -> bool:
    return "\U0001f1e6" <= char <= "\U0001f1ff"


def _split_emoji_clusters(run: str) -> list[str]:
    """Split a run of Unicode emoji into individual clusters.

    Keeps ZWJ (U+200D) sequences and trailing variation selectors
    attached to the preceding base emoji, and pairs regional-indicator
    codepoints, so multi-codepoint emoji (family, flags, \u2026) stay together.
    """
    clusters: list[str] = []
    current = ""
    for char in run:
        joins = char in ("\u200d", "\ufe0f") or (current and current[-1] == "\u200d")
        # A regional indicator joins a preceding lone regional indicator
        # to form a two-letter flag.
        flag_pair = (
            _is_regional_indicator(char)
            and len(current) == 1
            and _is_regional_indicator(current)
        )
        if joins or flag_pair:
            current += char
        else:
            if current:
                clusters.append(current)
            current = char
    if current:
        clusters.append(current)
    return clusters


def render_visual_length(text: str) -> int:
    """Visual length for the Pillow renderer: each emoji counts as 1 char."""
    return sum(1 if kind == "emoji" else len(value)
               for kind, value in tokenize_for_render(text))
