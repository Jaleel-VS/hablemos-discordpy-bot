"""Paradigm data + selection helpers for the conjugation game.

Loads the precomputed ``conjugation_paradigms.json`` (built offline by
``scripts/generate_conjugation_paradigms.py`` from verbecc) exactly once at
import. The runtime never touches verbecc or the ML stack — it just reads this
JSON.

Everything the engine needs to *pose a question* and *know the answer* lives
here: the verb sets, the tense catalog, the pronoun list, a picker, and the
teaching copy (tense explanations, pronoun glosses, irregularity notes) that
turns a right/wrong flash into something a learner can act on.
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
#: verb -> {"english": str, "forms": {tense: {pronoun: form}},
#:          "notes": {tense: str}, "classes": [str]} (notes/classes optional).
VERBS: dict[str, dict[str, Any]] = _raw["verbs"]

_TENSE_KEYS = set(TENSES)
_PRONOUN_SET = set(PRONOUNS)

#: Surface pronouns that share a paradigm slot. ``usted`` conjugates like
#: ``él``; ``ustedes`` like ``ellos``. The slot is what we grade and track; the
#: variant is only what the player *sees*, so they learn the mapping.
PRONOUN_VARIANTS: dict[str, list[str]] = {
    "yo": ["yo"],
    "tú": ["tú"],
    "él": ["él", "ella", "usted"],
    "nosotros": ["nosotros", "nosotras"],
    "vosotros": ["vosotros", "vosotras"],
    "ellos": ["ellos", "ellas", "ustedes"],
}
_VARIANT_TO_SLOT: dict[str, str] = {
    v: slot for slot, variants in PRONOUN_VARIANTS.items() for v in variants
}

#: English gloss per surface pronoun (shown next to the prompt).
PRONOUN_ENGLISH: dict[str, str] = {
    "yo": "I",
    "tú": "you (informal)",
    "él": "he",
    "ella": "she",
    "usted": "you (formal)",
    "nosotros": "we",
    "nosotras": "we (f.)",
    "vosotros": "you all (Spain)",
    "vosotras": "you all (f., Spain)",
    "ellos": "they",
    "ellas": "they (f.)",
    "ustedes": "you all",
}

#: Learner-facing explanation per tense: English name, one-line "when to use
#: it", and an example with ``hablar``. Keyed by canonical tense key; a tense
#: present in the JSON but missing here still works (label-only).
TENSE_META: dict[str, dict[str, str]] = {
    "presente": {
        "english": "Present",
        "hint": "What happens now or habitually: \"I speak\", \"I am speaking\".",
        "example": "yo hablo · tú hablas · él habla",
    },
    "pretérito": {
        "english": "Preterite",
        "hint": "A completed past action: \"I spoke\" (yesterday, once, done).",
        "example": "yo hablé · tú hablaste · él habló",
    },
    "imperfecto": {
        "english": "Imperfect",
        "hint": "Ongoing or habitual past: \"I was speaking\", \"I used to speak\".",
        "example": "yo hablaba · tú hablabas · él hablaba",
    },
    "futuro": {
        "english": "Future",
        "hint": "What will happen: \"I will speak\". Add the ending to the infinitive.",
        "example": "yo hablaré · tú hablarás · él hablará",
    },
    "condicional": {
        "english": "Conditional",
        "hint": "What would happen: \"I would speak\". Infinitive + -ía endings.",
        "example": "yo hablaría · tú hablarías · él hablaría",
    },
    "subjuntivo": {
        "english": "Present subjunctive",
        "hint": "Wishes, doubts, emotions: \"(I hope) that I speak\". Opposite vowel endings.",
        "example": "que yo hable · que tú hables · que él hable",
    },
}


def tense_english(tense: str) -> str:
    """English name for a tense key (falls back to the Spanish label)."""
    return TENSE_META.get(tense, {}).get("english") or TENSES.get(tense, tense)


#: Teaching order for the setup screen (the JSON is sorted alphabetically).
#: Tenses present in the data but not listed here follow, in data order.
TENSE_ORDER: list[str] = ["presente", "pretérito", "imperfecto", "futuro", "condicional", "subjuntivo"]


def tense_catalog() -> list[dict[str, str]]:
    """Every tense with its labels/hints, in teaching order (for the setup screen)."""
    ordered = [k for k in TENSE_ORDER if k in TENSES] + [k for k in TENSES if k not in TENSE_ORDER]
    return [
        {
            "key": key,
            "label": TENSES[key],
            "english": tense_english(key),
            "hint": TENSE_META.get(key, {}).get("hint", ""),
            "example": TENSE_META.get(key, {}).get("example", ""),
        }
        for key in ordered
    ]


def verb_note(verb: str, tense: str) -> str:
    """Irregularity note for a verb/tense (``""`` when the form is regular)."""
    notes = VERBS.get(verb, {}).get("notes")
    if not isinstance(notes, dict):
        return ""
    note = notes.get(tense, "")
    return note if isinstance(note, str) else ""


def paradigm_row(verb: str, tense: str) -> dict[str, str]:
    """All six forms of a verb in one tense (for the post-miss reveal)."""
    forms = VERBS.get(verb, {}).get("forms", {}).get(tense, {})
    return {p: forms[p] for p in PRONOUNS if p in forms}


@dataclass(frozen=True)
class Question:
    """One conjugation prompt and its authoritative answer.

    ``expected`` is the answer; it stays server-side (sealed) and is never put
    in a client view until the answer has been submitted.

    ``pronoun`` is the paradigm *slot* (``él``); ``shown`` is the surface
    pronoun the player sees (``usted``) — identical unless the config enabled
    formal/feminine variants.
    """

    verb: str
    english: str
    tense: str  # canonical key, e.g. "pretérito"
    pronoun: str
    expected: str
    shown: str = ""

    @property
    def display_pronoun(self) -> str:
        return self.shown or self.pronoun

    def prompt(self) -> dict[str, str]:
        """Answer-free view of the question (what the client renders)."""
        shown = self.display_pronoun
        return {
            "verb": self.verb,
            "english": self.english,
            "tense": self.tense,
            "tense_label": TENSES.get(self.tense, self.tense),
            "tense_english": tense_english(self.tense),
            "pronoun": shown,
            "pronoun_english": PRONOUN_ENGLISH.get(shown, ""),
        }

    def reveal(self) -> dict[str, Any]:
        """Post-answer teaching card: the answer, why it's irregular, the row."""
        return {
            "expected": self.expected,
            "note": verb_note(self.verb, self.tense),
            "row": paradigm_row(self.verb, self.tense),
        }

    def as_state(self) -> dict[str, str]:
        """Full serialization (includes the answer) for sealed state."""
        return {
            "verb": self.verb,
            "english": self.english,
            "tense": self.tense,
            "pronoun": self.pronoun,
            "shown": self.display_pronoun,
            "expected": self.expected,
        }

    @classmethod
    def from_state(cls, cur: dict[str, Any]) -> Question:
        """Rebuild from ``as_state`` output (missing optional keys tolerated)."""
        return cls(
            verb=cur["verb"],
            english=cur.get("english", ""),
            tense=cur["tense"],
            pronoun=cur["pronoun"],
            expected=cur["expected"],
            shown=cur.get("shown", "") or cur["pronoun"],
        )


def expected_form(verb: str, tense: str, pronoun: str) -> str | None:
    """The canonical conjugated form, or ``None`` if the combo isn't in data."""
    try:
        return VERBS[verb]["forms"][tense][_VARIANT_TO_SLOT.get(pronoun, pronoun)]
    except KeyError:
        return None


def make_question(verb: str, tense: str, pronoun: str, *, shown: str = "") -> Question | None:
    """Build a :class:`Question`, or ``None`` if the combo has no stored form.

    ``pronoun`` may be a surface variant (``usted``); it is normalized to its
    slot and the variant kept as ``shown``.
    """
    slot = _VARIANT_TO_SLOT.get(pronoun, pronoun)
    form = expected_form(verb, tense, slot)
    if form is None:
        return None
    english = VERBS.get(verb, {}).get("english", "")
    return Question(
        verb=verb, english=english, tense=tense, pronoun=slot, expected=form,
        shown=shown or pronoun,
    )


@dataclass(frozen=True)
class Config:
    """A validated game configuration (which verbs/tenses/pronouns to drill).

    * ``strict``   — accents required: a ``close`` match scores as wrong.
    * ``variants`` — show ``usted``/``ella``/``ustedes`` etc. for the same
                     slots so the learner practises the pronoun → person map.
    * ``items``    — for the untimed set mode: stop after this many prompts
                     (``0`` = open-ended, finish on demand).
    * ``verbs_override`` — explicit verb list (review mode drills the
                     player's own misses instead of a named set).
    """

    verb_set: str
    tenses: list[str]
    pronouns: list[str]
    strict: bool = False
    variants: bool = False
    items: int = 0
    verbs_override: tuple[str, ...] = ()

    @property
    def verbs(self) -> list[str]:
        if self.verbs_override:
            return list(self.verbs_override)
        return SETS[self.verb_set]

    def shown_pronoun(self, slot: str) -> str:
        """Pick the surface pronoun to display for a slot."""
        if not self.variants:
            return slot
        return secrets.choice(PRONOUN_VARIANTS.get(slot, [slot]))

    def as_state(self) -> dict[str, Any]:
        return {
            "verb_set": self.verb_set,
            "tenses": self.tenses,
            "pronouns": self.pronouns,
            "strict": self.strict,
            "variants": self.variants,
            "items": self.items,
            "verbs_override": list(self.verbs_override),
        }

    @classmethod
    def from_state(cls, cfg: dict[str, Any]) -> Config:
        """Rebuild from sealed state; tolerant of pre-upgrade games."""
        override = cfg.get("verbs_override")
        return cls(
            verb_set=cfg.get("verb_set", "high-frequency"),
            tenses=cfg.get("tenses") or list(TENSES),
            pronouns=cfg.get("pronouns") or list(PRONOUNS),
            strict=bool(cfg.get("strict", False)),
            variants=bool(cfg.get("variants", False)),
            items=int(cfg.get("items", 0) or 0),
            verbs_override=tuple(v for v in override if isinstance(v, str) and v in VERBS)
            if isinstance(override, list) else (),
        )


#: Longest "set mode" a client may request (keeps a sealed game bounded).
MAX_ITEMS = 50
#: Cap on an explicit review verb list.
MAX_REVIEW_VERBS = 40


def default_config() -> Config:
    """Sensible freeplay defaults: common verbs, all tenses, no vosotros."""
    return Config(
        verb_set="high-frequency",
        tenses=list(TENSES),
        pronouns=[p for p in PRONOUNS if p != "vosotros"],
    )


def _str_list(raw: Any, allowed: set[str]) -> list[str]:
    """Filter an untrusted list to known string keys (order kept, deduped)."""
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        # isinstance before membership: an unhashable element would TypeError.
        if isinstance(item, str) and item in allowed and item not in out:
            out.append(item)
    return out


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
    if not isinstance(verb_set, str) or verb_set not in SETS or not SETS[verb_set]:
        verb_set = base.verb_set

    tenses = _str_list(options.get("tenses"), _TENSE_KEYS) or base.tenses
    pronouns = _str_list(options.get("pronouns"), _PRONOUN_SET) or base.pronouns

    items_raw = options.get("items", 0)
    items = items_raw if isinstance(items_raw, int) and not isinstance(items_raw, bool) else 0
    items = max(0, min(items, MAX_ITEMS))

    # Review mode: the client sends the verbs it wants to drill (its own misses).
    # Unknown verbs are dropped; an empty result means "no override".
    review = tuple(_str_list(options.get("verbs"), set(VERBS))[:MAX_REVIEW_VERBS])

    return Config(
        verb_set=verb_set,
        tenses=tenses,
        pronouns=pronouns,
        strict=options.get("strict") is True,
        variants=options.get("variants") is True,
        items=items,
        verbs_override=review,
    )


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
        q = make_question(verb, tense, pronoun, shown=config.shown_pronoun(pronoun))
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
