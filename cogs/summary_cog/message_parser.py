"""
Message link parser for Discord message URLs
"""
import logging

logger = logging.getLogger(__name__)

def parse_message_link(link: str) -> tuple[int | None, int | None, int | None]:
    """
    Parse a Discord message link to extract guild_id, channel_id, and message_id

    Discord message links follow the format:
    https://discord.com/channels/{guild_id}/{channel_id}/{message_id}

    Args:
        link: Discord message link URL

    Returns:
        Tuple of (guild_id, channel_id, message_id) or (None, None, None) if invalid
    """
    if not link or not isinstance(link, str):
        return None, None, None

    # Remove whitespace
    link = link.strip()

    # Check if it starts with the Discord domain
    if not link.startswith("https://discord.com/channels/") and not link.startswith("http://discord.com/channels/"):
        logger.debug("Invalid message link format: %s", link)
        return None, None, None

    # Split the URL and extract parts
    try:
        # Remove any query parameters (e.g., ?key=value)
        link_without_query = link.split('?')[0]

        # Split by '/' and get the relevant parts
        parts = link_without_query.split('/')

        # Expected format: ['https:', '', 'discord.com', 'channels', guild_id, channel_id, message_id]
        if len(parts) < 7:
            logger.debug("Message link has insufficient parts: %s", link)
            return None, None, None

        guild_id = int(parts[4])
        channel_id = int(parts[5])
        message_id = int(parts[6])

        logger.debug("Parsed message link: guild=%s, channel=%s, message=%s", guild_id, channel_id, message_id)
        return guild_id, channel_id, message_id

    except (ValueError, IndexError) as e:
        logger.debug("Error parsing message link '%s': %s", link, e)
        return None, None, None

def validate_message_link(link: str) -> bool:
    """Return True if ``link`` is a Discord message URL."""
    guild_id, channel_id, message_id = parse_message_link(link)
    return all(v is not None for v in (guild_id, channel_id, message_id))


def collect_range_messages(
    history: list,
    start_msg,
    end_msg,
    *,
    include_link: bool = False,
    guild_id: int | None = None,
    channel_id: int | None = None,
) -> list[dict]:
    """Inclusive [start, end] user messages, keyed by id so boundaries
    are never appended twice (same-message range or API-inclusive history).
    """
    collected: dict[int, dict] = {}

    def _maybe_add(msg) -> None:
        if msg.author.bot or not msg.content.strip():
            return
        if msg.id in collected:
            return
        row = {
            "author": msg.author.display_name,
            "content": msg.content,
            "timestamp": msg.created_at,
        }
        if include_link and guild_id is not None and channel_id is not None:
            row["link"] = (
                f"https://discord.com/channels/{guild_id}/{channel_id}/{msg.id}"
            )
        collected[msg.id] = row

    for msg in history:
        _maybe_add(msg)
    _maybe_add(start_msg)
    _maybe_add(end_msg)
    return sorted(collected.values(), key=lambda m: m["timestamp"])
