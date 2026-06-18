"""Prompts used by ``practice_cog``.

One stateless prompt: :data:`PRACTICE_SENTENCE_PROMPT`. Given a target
word + translation + language, it asks Gemini to generate a natural
A2-B1 sentence and returns the (sentence, sentence_with_blank) tuple
suitable for cloze-style practice cards.

The cloze blank is computed from the original word at parse time;
generation that doesn't include the target word is rejected (parse
returns ``None``).
"""
import re
from dataclasses import dataclass

from cogs.utils.gemini import Prompt

SENTENCE_TEMPLATE = """Generate a natural, contextual sentence in {language} using the word "{word}" (meaning: {translation}).

Requirements:
- Sentence should be A2-B1 level difficulty
- Word should appear naturally in context (use the exact form "{word}")
- Sentence should be 8-15 words long
- Do not include the translation in the sentence
- Do not include any explanations or notes

Return ONLY the sentence in {language}, nothing else.

Example for Spanish word "hablar" (to speak):
Mi hermana puede hablar tres idiomas diferentes."""


@dataclass(frozen=True, slots=True)
class PracticeWord:
    """Input for :class:`PracticeSentencePrompt`."""
    word: str
    translation: str
    language: str  # "spanish" or "english"


def _language_name(language: str) -> str:
    return "Spanish" if language == "spanish" else "English"


class PracticeSentencePrompt(Prompt[PracticeWord, tuple[str, str] | None]):
    """Generate a cloze-ready practice sentence for a target word.

    Output is ``(full_sentence, sentence_with_blank)`` on success, or
    ``None`` if Gemini's response doesn't contain the target word
    (validated via word-boundary regex).
    """

    feature = "practice"
    temperature = 0.7
    max_output_tokens = 100

    def render(self, inp: PracticeWord) -> str:
        return SENTENCE_TEMPLATE.format(
            language=_language_name(inp.language),
            word=inp.word,
            translation=inp.translation,
        )

    def parse(self, text: str, inp: PracticeWord) -> tuple[str, str] | None:
        if not text:
            return None
        sentence = text.strip()
        if not sentence:
            return None
        pattern = r"\b" + re.escape(inp.word) + r"\b"
        match = re.search(pattern, sentence, re.IGNORECASE)
        if match is None:
            return None
        sentence_with_blank = sentence[: match.start()] + "___" + sentence[match.end() :]
        return sentence, sentence_with_blank


PRACTICE_SENTENCE_PROMPT = PracticeSentencePrompt()


__all__ = [
    "PRACTICE_SENTENCE_PROMPT",
    "PracticeSentencePrompt",
    "PracticeWord",
]
