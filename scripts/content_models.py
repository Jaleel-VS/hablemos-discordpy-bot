"""Typed JSON contracts shared by offline content generation scripts."""
from __future__ import annotations

from typing import Literal, TypedDict

Verdict = Literal["ok", "suspect"]


class ClozeCard(TypedDict):
    """Validated cloze card before an ID is assigned."""

    target: str
    cloze: str
    answer: str
    context: str
    distractors: list[str]
    difficulty: str


class StoredClozeCard(ClozeCard):
    """Validated cloze card stored in the committed corpus."""

    id: str


class ClozeCorpus(TypedDict, total=False):
    """Stored cloze corpus fields used by the offline scripts."""

    cards: list[StoredClozeCard]
    meta: dict[str, int | str | bool | dict[str, int]]


class ReviewVerdict(TypedDict):
    """Validated cloze semantic-review result."""

    verdict: Verdict
    reasons: list[str]
    suggested_answer: str


class ReviewedClozeCard(StoredClozeCard):
    """Quarantined card carrying its validated review result."""

    _review: ReviewVerdict


class RawPhrasalEntry(TypedDict, total=False):
    """Untrusted source entry consumed by the phrasal generator."""

    frequency: int
    examples: list[str]
    synonyms: list[str]
    descriptions: list[str]
    derivatives: list[str]


class PhrasalVerb(TypedDict, total=False):
    """Validated phrasal-verb corpus entry."""

    id: str
    verb: str
    particle: str
    base: str
    definitions: list[str]
    gloss_es: str | None
    example: str
    example_answer: str
    forms: list[str]
    difficulty: str
    frequency: int
    distractors_particle: list[str]


class PhrasalCorpus(TypedDict):
    """Stored phrasal-verb corpus."""

    meta: dict[str, int | str | bool | dict[str, int]]
    verbs: list[PhrasalVerb]


class PhrasalReview(TypedDict):
    """Validated phrasal semantic-review result."""

    verdict: Literal["ok", "fix", "broken"]
    reasons: list[str]
    suggested_gloss: str
    suggested_difficulty: str
    suggested_definition: str
