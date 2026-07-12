"""Answer comparison for the conjugation game.

A learner types a verb form; we grade it against the expected form with three
outcomes rather than a boolean, because accents are the single most common
Spanish mistake and blocking on them frustrates beginners:

* ``EXACT``  — matches including accents. Full credit, no note.
* ``CLOSE``  — matches once accents are stripped (e.g. ``hable`` for ``hablé``).
  Counts as correct but the UI flags the accent so the learner still sees it.
* ``WRONG``  — different stem/ending. Incorrect.

Ñ is a distinct letter and must survive accent-stripping, so we reuse the same
NFD ñ-protection the Wordle normalizer uses (decomposing ``ñ`` would otherwise
split it into ``n`` + combining tilde and lose it).
"""
from __future__ import annotations

import unicodedata
from enum import StrEnum

# Private-use codepoint that shields ñ/Ñ from the combining-mark strip.
_SENTINEL = ""


class Match(StrEnum):
    """Grading outcome for a submitted answer."""

    EXACT = "exact"
    CLOSE = "close"  # correct except for accents
    WRONG = "wrong"


def _strip_accents(text: str) -> str:
    """Lowercase and strip accents, preserving ñ as one letter."""
    shielded = text.strip().lower().replace("ñ", _SENTINEL)
    decomposed = unicodedata.normalize("NFD", shielded)
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return stripped.replace(_SENTINEL, "ñ")


def _clean(text: str) -> str:
    """Trim and collapse internal whitespace; keep the accented, lowercased form."""
    return " ".join(text.strip().lower().split())


def grade(guess: str, expected: str) -> Match:
    """Grade ``guess`` against the canonical ``expected`` form.

    ``expected`` is assumed already canonical (accented, lowercase) as stored in
    the paradigm data. Comparison is deliberately whitespace- and case-tolerant.
    """
    g_exact = _clean(guess)
    e_exact = _clean(expected)
    if not g_exact:
        return Match.WRONG
    if g_exact == e_exact:
        return Match.EXACT
    if _strip_accents(g_exact) == _strip_accents(e_exact):
        return Match.CLOSE
    return Match.WRONG
