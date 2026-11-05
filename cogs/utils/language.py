"""Spanish/English message detection with caller-owned length policy."""
import re

from lingua import Language, LanguageDetectorBuilder

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
    flags=re.UNICODE,
)

_SUPPORTED_LANGUAGES = {Language.SPANISH: 'es', Language.ENGLISH: 'en'}

# Gate against confusable neighbours first, then judge ES vs EN confidence.
_GATE_DETECTOR = LanguageDetectorBuilder.from_languages(
    *_SUPPORTED_LANGUAGES,
    Language.PORTUGUESE,
    Language.ITALIAN,
    Language.FRENCH,
    Language.CATALAN,
    Language.GERMAN,
).with_preloaded_language_models().build()
_SUPPORTED_DETECTOR = LanguageDetectorBuilder.from_languages(
    *_SUPPORTED_LANGUAGES,
).with_preloaded_language_models().build()


def detect_message_language(
    message_content: str, *, min_length: int, min_confidence: float = 0.8,
) -> str | None:
    """Return 'es' or 'en', or None for short, unsupported or uncertain text.

    Length is measured after stripping custom Discord and Unicode emojis.
    """
    content_no_custom_emojis = CUSTOM_EMOJI_PATTERN.sub('', message_content)
    clean_content = UNICODE_EMOJI_PATTERN.sub('', content_no_custom_emojis).strip()
    if len(clean_content) < min_length:
        return None

    language = _GATE_DETECTOR.detect_language_of(clean_content)
    if language not in _SUPPORTED_LANGUAGES:
        return None

    confidence = _SUPPORTED_DETECTOR.compute_language_confidence(clean_content, language)
    if confidence < min_confidence:
        return None
    return _SUPPORTED_LANGUAGES[language]
