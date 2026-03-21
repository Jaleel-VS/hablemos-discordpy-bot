"""
Gemini API client for generating practice sentences.
"""
import os
import re
import logging
import random
import asyncio

from google import genai
from google.genai import types
from cogs.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

class PracticeGeminiClient:
    """Wrapper for Google Gemini API for sentence generation"""

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

    def __init__(self):
        """Initialize Gemini client for sentence generation"""
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is required")

        self.client = genai.Client(api_key=api_key)
        self.model_name = 'gemini-2.0-flash-lite'
        self.rate_limiter = RateLimiter(requests_per_minute=15)

        logger.info("Practice Gemini client initialized successfully")

    async def generate_sentence(self, word: str, translation: str,
                                language: str, max_retries: int = 3) -> tuple[str, str | None]:
        """
        Generate a sentence containing the target word.

        Args:
            word: Target word to include in sentence
            translation: Meaning of the word
            language: Language for the sentence (spanish/english)
            max_retries: Maximum retry attempts

        Returns:
            Tuple of (full_sentence, sentence_with_blank) or None if failed
        """
        for attempt in range(max_retries):
            try:
                await self.rate_limiter.wait_if_needed()

                # Create prompt
                lang_name = "Spanish" if language == "spanish" else "English"
                prompt = self.SENTENCE_PROMPT.format(
                    language=lang_name,
                    word=word,
                    translation=translation
                )

                # Generate sentence
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.7,
                        top_p=0.9,
                        top_k=40,
                        max_output_tokens=100,
                    )
                )

                sentence = response.text.strip()

                # Validate sentence contains the word
                if not self._contains_word(sentence, word):
                    logger.warning(f"Generated sentence doesn't contain word '{word}': {sentence}")
                    continue

                # Create blank version
                sentence_with_blank = self._create_blank(sentence, word)

                if sentence_with_blank:
                    logger.info(f"Successfully generated sentence for '{word}'")
                    return sentence, sentence_with_blank
                else:
                    logger.warning(f"Failed to create blank for '{word}' in: {sentence}")

            except Exception as e:
                logger.error(f"Gemini API error (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    await asyncio.sleep(wait_time)

        return None

    def _contains_word(self, sentence: str, word: str) -> bool:
        """Check if sentence contains the word (case-insensitive)"""
        # Use word boundary regex for accurate matching
        pattern = r'\b' + re.escape(word) + r'\b'
        return bool(re.search(pattern, sentence, re.IGNORECASE))

    def _create_blank(self, sentence: str, word: str) -> str | None:
        """Replace the word with ___ in the sentence"""
        # Use regex to replace word with blank (case-insensitive, preserve case)
        pattern = r'\b' + re.escape(word) + r'\b'
        match = re.search(pattern, sentence, re.IGNORECASE)

        if match:
            # Replace the matched word with ___
            return sentence[:match.start()] + "___" + sentence[match.end():]

        return None
