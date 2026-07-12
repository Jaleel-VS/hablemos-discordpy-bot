"""Paradigm data + selection helpers for the conjugation game.

Loads the precomputed ``conjugation_paradigms.json`` (built offline by
``scripts/generate_conjugation_paradigms.py`` from verbecc) exactly once at
import. The runtime never touches verbecc or the ML stack — it just reads this
JSON.

Everything the engine needs to *pose a question* and *know the answer* lives
here: the verb sets, the tense catalog, the pronoun list, and a picker.
"""
from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_DATA = Path(__file__).resolve().parent.parent / "data" / "conjugation_paradigms.json"

_raw: dict[str, Any] = json.loads(_DATA.read_text(encoding="utf-8"))

#: Canonical pronoun slots, in teaching order (yo, tú, él, nosotros, …).
PRONOUNS: list[str] = _raw["pronouns"]
#: tense key -> display label ("pretérito" -> "Pretérito").
TENSES: dict[str, str] = _raw["tenses"]
#: set key -> list of verb infinitives.
SETS: dict[str, list[str]] = _raw["sets"]
#: verb -> {"english": str, "forms": {tense: {pronoun: form}}}.
VERBS: dict[str, dict[str, Any]] = _raw["verbs"]

_TENSE_KEYS = set(TENSES)
_PRONOUN_SET = set(PRONOUNS)


@dataclass(frozen=True)
class Question:
    """One conjugation prompt and its authoritative answer.

    ``expected`` is the answer; it stays server-side (sealed) and is never put
    in a client view until the answer has been submitted.
    """

    verb: str
    english: str
    tense: str  # canonical key, e.g. "pretérito"
    pronoun: str
    expected: str

    def prompt(self) -> dict[str, str]:
        """Answer-free view of the question (what the client renders)."""
        return {
            "verb": self.verb,
            "english": self.english,
            "tense": self.tense,
            "tense_label": TENSES.get(self.tense, self.tense),
            "pronoun": self.pronoun,
        }

    def as_state(self) -> dict[str, str]:
        """Full serialization (includes the answer) for sealed state."""
        return {
            "verb": self.verb,
            "english": self.english,
            "tense": self.tense,
            "pronoun": self.pronoun,
            "expected": self.expected,
        }


def expected_form(verb: str, tense: str, pronoun: str) -> str | None:
    """The canonical conjugated form, or ``None`` if the combo isn't in data."""
    try:
        return VERBS[verb]["forms"][tense][pronoun]
    except KeyError:
        return None


def make_question(verb: str, tense: str, pronoun: str) -> Question | None:
    """Build a :class:`Question`, or ``None`` if the combo has no stored form."""
    form = expected_form(verb, tense, pronoun)
    if form is None:
        return None
    english = VERBS.get(verb, {}).get("english", "")
    return Question(verb=verb, english=english, tense=tense, pronoun=pronoun, expected=form)


@dataclass(frozen=True)
class Config:
    """A validated game configuration (which verbs/tenses/pronouns to drill)."""

    verb_set: str
    tenses: list[str]
    pronouns: list[str]

    @property
    def verbs(self) -> list[str]:
        return SETS[self.verb_set]


def default_config() -> Config:
    """Sensible freeplay defaults: common verbs, all tenses, no vosotros."""
    return Config(
        verb_set="high-frequency",
        tenses=list(TENSES),
        pronouns=[p for p in PRONOUNS if p != "vosotros"],
    )


def resolve_config(options: dict[str, Any] | None) -> Config:
    """Turn untrusted client ``options`` into a valid :class:`Config`.

    Every field falls back to a default when missing or invalid, so a hostile or
    partial payload can never produce an empty pool. This is the single place
    ``None``/garbage is normalized — the engine downstream gets a concrete
    ``Config`` it can trust.
    """
    base = default_config()
    if not isinstance(options, dict):
        return base

    verb_set = options.get("set")
    if verb_set not in SETS or not SETS[verb_set]:
        verb_set = base.verb_set

    raw_tenses = options.get("tenses")
    tenses = [t for t in raw_tenses if t in _TENSE_KEYS] if isinstance(raw_tenses, list) else []
    if not tenses:
        tenses = base.tenses

    raw_pronouns = options.get("pronouns")
    pronouns = (
        [p for p in raw_pronouns if p in _PRONOUN_SET] if isinstance(raw_pronouns, list) else []
    )
    if not pronouns:
        pronouns = base.pronouns

    return Config(verb_set=verb_set, tenses=tenses, pronouns=pronouns)


def pick_question(config: Config, *, avoid: Question | None = None) -> Question:
    """Draw a random question from the configured pools.

    Uses ``secrets.choice`` (no global RNG state, matching the Wordle engine).
    Retries a few times to avoid immediately repeating the same prompt; falls
    back to any valid combo so it always returns a question.
    """
    for _ in range(8):
        verb = secrets.choice(config.verbs)
        tense = secrets.choice(config.tenses)
        pronoun = secrets.choice(config.pronouns)
        q = make_question(verb, tense, pronoun)
        if q is None:
            continue
        if avoid is not None and (q.verb, q.tense, q.pronoun) == (
            avoid.verb, avoid.tense, avoid.pronoun,
        ):
            continue
        return q
    # Deterministic fallback: first valid combo in the pools.
    for verb in config.verbs:
        for tense in config.tenses:
            for pronoun in config.pronouns:
                q = make_question(verb, tense, pronoun)
                if q is not None:
                    return q
    raise RuntimeError("no valid question in configured pools")  # data is broken
