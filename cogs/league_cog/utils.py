"""
Shared utilities for the Language League system.

This module contains helper functions and constants used by both
the main league cog and the admin cog.
"""
import re
import logging
from typing import Optional
from langdetect import detect, LangDetectException
from cogs.league_cog.config import LANGUAGE, RATE_LIMITS

logger = logging.getLogger(__name__)

# Regex patterns for message filtering
CUSTOM_EMOJI_PATTERN = re.compile(r'<a?:\w+:\d+>')
UNICODE_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map symbols
    "\U0001F1E0-\U0001F1FF"  # flags (iOS)
    "\U00002702-\U000027B0"  # dingbats
    "\U000024C2-\U0001F251"  # enclosed characters
    "\U0001F900-\U0001F9FF"  # supplemental symbols
    "\U0001FA00-\U0001FA6F"  # extended pictographs
    "]+",
    flags=re.UNICODE
)


def detect_message_language(message_content: str) -> Optional[str]:
    """
    Detect the language of a message using langdetect.

    This function:
    1. Removes all Discord custom emojis and Unicode emojis
    2. Checks if the remaining content meets minimum length
    3. Detects language using langdetect
    4. Only returns 'es' or 'en', None for other languages

    Args:
        message_content: The raw message content to analyze

    Returns:
        'es' for Spanish, 'en' for English, None if uncertain or error
    """
    # Remove custom Discord emojis (format: <:name:id> or <a:name:id>)
    content_no_custom_emojis = CUSTOM_EMOJI_PATTERN.sub('', message_content)

    # Remove Unicode emojis
    content_no_emojis = UNICODE_EMOJI_PATTERN.sub('', content_no_custom_emojis)

    # Strip whitespace and check if there's actual text content
    clean_content = content_no_emojis.strip()

    # Skip very short messages or emoji-only messages
    if len(clean_content) < RATE_LIMITS.MIN_MESSAGE_LENGTH:
        return None

    try:
        detected_lang = detect(clean_content)

        # Only return if we detected Spanish or English
        if detected_lang in [LANGUAGE.SPANISH_CODE, LANGUAGE.ENGLISH_CODE]:
            return detected_lang

        return None
    except LangDetectException:
        # Detection failed (empty string, etc.)
        return None
    except Exception as e:
        logger.error(f"Language detection error: {e}")
        return None
