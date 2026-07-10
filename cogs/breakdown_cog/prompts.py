"""Gemini prompts for the breakdown cog.

Each prompt is a stateless singleton — instantiate once at import time
and pass the same instance to ``bot.gemini.run`` on every call.
"""
from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field

from cogs.utils.gemini import Prompt

# ── Pydantic models for structured output ──


class WordBreakdown(BaseModel):
    """Analysis of a single word or multi-word unit."""

    word: str = Field(description="The word or phrase being analyzed")
    part_of_speech: str = Field(
        description="Part of speech: noun, verb, adjective, adverb, "
        "preposition, article, pronoun, conjunction, etc."
    )
    grammatical_role: str = Field(
        description="Grammatical role: subject, direct object, indirect object, "
        "predicate, complement, modifier, determiner, etc."
    )
    translation: str = Field(
        description="Translation to the explanation language"
    )
    notes: str = Field(
        description="Extra grammatical info: verb tense/mood/person, "
        "noun gender/number, agreement details. Empty string if none."
    )


class ClauseBreakdown(BaseModel):
    """Analysis of a single clause within the sentence."""

    clause_text: str = Field(description="The clause text as it appears")
    clause_type: str = Field(
        description="Type of clause: main clause, subordinate clause, "
        "relative clause, conditional clause, etc."
    )
    words: list[WordBreakdown] = Field(
        description="Word-by-word breakdown of this clause"
    )


class SentenceBreakdown(BaseModel):
    """Complete grammatical breakdown of a sentence."""

    correction: str | None = Field(
        default=None,
        description="Corrected sentence if spelling mistakes were found. "
        "null if no corrections needed.",
    )
    clauses: list[ClauseBreakdown] = Field(
        description="Clause-level breakdown of the sentence"
    )
    full_translation: str = Field(
        description="Natural translation of the full sentence"
    )


# ── Prompt input ──


@dataclass(frozen=True)
class BreakdownInput:
    """Input to the breakdown prompt."""

    sentence: str
    detected_language: str  # 'es' or 'en'


# ── Prompt class ──


class BreakdownPrompt(Prompt[BreakdownInput, SentenceBreakdown]):
    """Clause-level + word-level sentence breakdown (structured output).

    Input: a sentence and its detected language.
    Output: a validated SentenceBreakdown model.
    """

    feature = "breakdown"
    temperature = 0.3
    max_output_tokens = 4096
    response_mime_type = "application/json"
    response_schema = SentenceBreakdown

    def render(self, inp: BreakdownInput) -> str:
        if inp.detected_language == "es":
            source_lang = "Spanish"
            explain_lang = "English"
        else:
            source_lang = "English"
            explain_lang = "Spanish"

        return (
            f"You are a language tutor helping learners understand sentence structure.\n\n"
            f"The user submitted a sentence in {source_lang}. "
            f"Provide the grammatical breakdown with all explanations and "
            f"translations in {explain_lang}.\n\n"
            f"Instructions:\n"
            f"- If there are minor spelling mistakes, provide the corrected "
            f"sentence in the 'correction' field. Otherwise leave it null.\n"
            f"- Break the sentence into clauses (main, subordinate, relative, etc.).\n"
            f"- For each clause, analyze every word or multi-word unit:\n"
            f"  - Part of speech\n"
            f"  - Grammatical role in the clause\n"
            f"  - Translation to {explain_lang}\n"
            f"  - For verbs: include tense, mood, person/number in notes\n"
            f"  - For nouns/adjectives: include gender/number agreement in notes\n"
            f"  - Leave notes empty string if no extra info applies\n"
            f"- Provide a natural full translation at the end.\n\n"
            f"Sentence: \"{inp.sentence}\""
        )

    def parse(self, text: str, inp: BreakdownInput) -> SentenceBreakdown:
        return SentenceBreakdown.model_validate_json(text)


BREAKDOWN_PROMPT = BreakdownPrompt()
