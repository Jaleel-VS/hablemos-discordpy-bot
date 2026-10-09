"""Data gate for wordle_lexicon.json — the learning card shown after every game.

The lexicon is LLM-generated then model-reviewed offline
(scripts/generate_wordle_lexicon.py); this test is the mechanical contract
that keeps a bad regeneration from shipping a wrong or empty card:

- every answer has exactly one entry with the full key set;
- ``display`` (the accented spelling) normalizes back to the answer, so the
  card can never show a different word than the one just played;
- ``display`` appears verbatim in the Spanish example;
- ``pos`` is from the closed set the UI labels;
- glosses and examples are non-empty.

All violations are collected and reported together.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.games.wordle.normalize import normalize
from app.games.wordle.words import ANSWERS

_LEXICON_PATH = Path(__file__).resolve().parent.parent / "app" / "games" / "data" / "wordle_lexicon.json"
_KEYS = {"display", "pos", "en", "example_es", "example_en", "lemma", "form"}
_POS = {"noun", "verb", "adjective", "adverb", "other"}


def _violations(answer: str, entry: object) -> list[str]:
    if not isinstance(entry, dict):
        return [f"{answer}: entry is not an object"]
    problems: list[str] = []
    if set(entry) != _KEYS:
        problems.append(f"{answer}: keys {sorted(set(entry) ^ _KEYS)} differ from contract")
        return problems
    display = entry["display"]
    if normalize(display) != answer:
        problems.append(f"{answer}: display {display!r} normalizes to {normalize(display)!r}")
    if display.lower() not in entry["example_es"].lower():
        problems.append(f"{answer}: {display!r} not in example_es {entry['example_es']!r}")
    if entry["pos"] not in _POS:
        problems.append(f"{answer}: pos {entry['pos']!r} not in {sorted(_POS)}")
    for field in ("en", "example_es", "example_en", "lemma"):
        if not str(entry[field]).strip():
            problems.append(f"{answer}: empty {field}")
    return problems


def test_lexicon_matches_answer_list_and_contract():
    lexicon = json.loads(_LEXICON_PATH.read_text(encoding="utf-8"))
    problems = [f"{w}: missing entry" for w in ANSWERS if w not in lexicon]
    problems += [f"{w}: entry for a word that is not an answer" for w in lexicon if w not in ANSWERS]
    for answer in ANSWERS:
        if answer in lexicon:
            problems += _violations(answer, lexicon[answer])
    assert not problems, f"{len(problems)} lexicon problems:\n" + "\n".join(problems[:40])
