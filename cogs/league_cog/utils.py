"""
Shared utilities for the Language League system.

This module contains helper functions and constants used by both
the main league cog and the admin cog.
"""
import logging
import re

from lingua import Language, LanguageDetectorBuilder

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

_LEAGUE_LANGUAGES = {
    Language.SPANISH: LANGUAGE.SPANISH_CODE,
    Language.ENGLISH: LANGUAGE.ENGLISH_CODE,
}

# Stage 1 picks the most likely language among ES/EN and their confusable
# neighbours, so Portuguese, French, etc. are rejected rather than forced into
# ES/EN. Stage 2 judges ES vs EN alone, where confidence is meaningful.
_GATE_DETECTOR = LanguageDetectorBuilder.from_languages(
    *_LEAGUE_LANGUAGES,
    Language.PORTUGUESE,
    Language.ITALIAN,
    Language.FRENCH,
    Language.CATALAN,
    Language.GERMAN,
).with_preloaded_language_models().build()
_LEAGUE_DETECTOR = LanguageDetectorBuilder.from_languages(
    *_LEAGUE_LANGUAGES,
).with_preloaded_language_models().build()


def detect_message_language(message_content: str) -> str | None:
    """
    Detect whether a message is Spanish or English.

    Emojis are stripped first; messages shorter than the minimum length, in
    another language, or below the confidence floor return None so short
    ambiguous slang ("No mames w") is not counted as the wrong language.

    Args:
        message_content: The raw message content to analyze

    Returns:
        'es' for Spanish, 'en' for English, None if uncertain
    """
    content_no_custom_emojis = CUSTOM_EMOJI_PATTERN.sub('', message_content)
    clean_content = UNICODE_EMOJI_PATTERN.sub('', content_no_custom_emojis).strip()

    if len(clean_content) < RATE_LIMITS.MIN_MESSAGE_LENGTH:
        return None

    language = _GATE_DETECTOR.detect_language_of(clean_content)
    if language not in _LEAGUE_LANGUAGES:
        return None

    confidence = _LEAGUE_DETECTOR.compute_language_confidence(clean_content, language)
    if confidence < LANGUAGE.MIN_CONFIDENCE:
        return None
    return _LEAGUE_LANGUAGES[language]
