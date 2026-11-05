"""Parse Discord message URLs for any cog."""
import re
from typing import NamedTuple

_LINK_RE = re.compile(
    r"^https?://(?:(?:canary|ptb)\.)?discord(?:app)?\.com/channels/(\d+)/(\d+)/(\d+)/?(?:\?.*)?$"
)


class MessageLink(NamedTuple):
    """IDs addressed by a Discord message URL."""

    guild_id: int
    channel_id: int
    message_id: int


def parse_message_link(link: str) -> MessageLink | None:
    """Return the IDs in a Discord message URL, or None if it isn't one."""
    match = _LINK_RE.match(link.strip())
    if match is None:
        return None
    return MessageLink(*(int(part) for part in match.groups()))
