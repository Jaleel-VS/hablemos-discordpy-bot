"""
Message link parser for Discord message URLs
"""
import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)


def parse_message_link(link: str) -> Tuple[Optional[int], Optional[int], Optional[int]]:
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
        logger.debug(f"Invalid message link format: {link}")
        return None, None, None

    # Split the URL and extract parts
    try:
        # Remove any query parameters (e.g., ?key=value)
        link_without_query = link.split('?')[0]

        # Split by '/' and get the relevant parts
        parts = link_without_query.split('/')

        # Expected format: ['https:', '', 'discord.com', 'channels', guild_id, channel_id, message_id]
        if len(parts) < 7:
            logger.debug(f"Message link has insufficient parts: {link}")
            return None, None, None

        guild_id = int(parts[4])
        channel_id = int(parts[5])
        message_id = int(parts[6])

        logger.debug(f"Parsed message link: guild={guild_id}, channel={channel_id}, message={message_id}")
        return guild_id, channel_id, message_id

    except (ValueError, IndexError) as e:
        logger.debug(f"Error parsing message link '{link}': {e}")
        return None, None, None


def validate_message_link(link: str) -> bool:
    """
    Validate if a string is a valid Discord message link

    Args:
        link: String to validate

    Returns:
        True if valid Discord message link, False otherwise
    """
    guild_id, channel_id, message_id = parse_message_link(link)
    return all([guild_id is not None, channel_id is not None, message_id is not None])
