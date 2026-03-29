"""Gemini client for generating practice sentences."""
import logging
import re

from cogs.utils.gemini_base import BaseGeminiClient

logger = logging.getLogger(__name__)

SENTENCE_PROMPT = """Generate a natural, contextual sentence in {language} using the word "{word}" (meaning: {translation}).

Requirements:
- Sentence should be A2-B1 level difficulty
- Word should appear naturally in context (use the exact form "{word}")
- Sentence should be 8-15 words long
- Do not include the translation in the sentence
- Do not include any explanations or notes

Return ONLY the sentence in {language}, nothing else.

Example for Spanish word "hablar" (to speak):
Mi hermana puede hablar tres idiomas diferentes."""


class PracticeGeminiClient(BaseGeminiClient):
    """Generates cloze-style practice sentences via Gemini."""

    async def generate_sentence(
        self, word: str, translation: str, language: str,
    ) -> tuple[str, str] | None:
        """Generate a sentence containing the target word.

        Returns (full_sentence, sentence_with_blank) or None.
        """
        lang_name = "Spanish" if language == "spanish" else "English"
        prompt = SENTENCE_PROMPT.format(language=lang_name, word=word, translation=translation)

        text = await self._generate_with_retry(
            prompt, temperature=0.7, max_output_tokens=100,
        )
        if not text:
            return None

        sentence = text.strip()

        # Validate word is present
        pattern = r'\b' + re.escape(word) + r'\b'
        match = re.search(pattern, sentence, re.IGNORECASE)
        if not match:
            logger.warning("Generated sentence missing word '%s': %s", word, sentence)
            return None

        sentence_with_blank = sentence[:match.start()] + "___" + sentence[match.end():]
        logger.info("Generated sentence for '%s'", word)
        return sentence, sentence_with_blank
