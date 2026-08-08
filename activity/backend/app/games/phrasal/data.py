"""Verb data + selection helpers for the phrasal-verb game.

Loads the precomputed ``phrasal_verbs.json`` (built offline by
``scripts/generate_phrasal_verbs.py`` from the WithEnglishWeCan dataset) once at
import. The runtime never calls an LLM — it just reads this JSON, the same rule
the conjugation and cloze games follow.

Everything the engine needs to *pose an item* and *know the answer* lives here:
the verb pool, the difficulty catalog, and the pickers (deterministic for daily,
random for freeplay).

A verb entry (see the generator for the full schema)::

    {
      "id": "pv-0001",
      "verb": "carry out",
      "particle": "out",
      "base": "carry",
      "definitions": ["to do a particular piece of work, research etc"],
      "gloss_es": null,
      "example": "An investigation is being ___ by the prison governor.",
      "example_answer": "carried out",
      "forms": ["carried out", "carries out", "carry out", "carrying out"],
      "distractors_particle": ["over", "on", "away"],
      "difficulty": "beginner"
    }
"""
from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_DATA = Path(__file__).resolve().parent.parent / "data" / "phrasal_verbs.json"

_raw: dict[str, Any] = json.loads(_DATA.read_text(encoding="utf-8")) if _DATA.exists() else {}

#: difficulty key -> display label.
DIFFICULTIES: dict[str, str] = _raw.get("difficulties", {
    "beginner": "Beginner",
    "intermediate": "Intermediate",
    "advanced": "Advanced",
})

#: All verbs, in file (ranked) order.
_ALL: list[dict[str, Any]] = _raw.get("verbs", [])

_DIFFICULTY_KEYS = set(DIFFICULTIES)

#: The two ways to blank the example sentence.
BLANK_MODES = ("particle", "whole")


@dataclass(frozen=True)
class Verb:
    """One phrasal verb and everything needed to pose/grade it.

    Answer material (``forms``, ``particle``) stays server-side (sealed) and is
    never placed in a client view until the item has been answered.
    """

    id: str
    verb: str
    particle: str
    base: str
    definitions: tuple[str, ...]
    gloss_es: str | None
    example: str
    example_answer: str
    forms: tuple[str, ...]
    distractors_particle: tuple[str, ...]
    difficulty: str

    def accepted_forms(self, blank_mode: str) -> list[str]:
        """The set of answers graded as correct for a given blank mode.

        - ``particle``: only the particle (the base verb is shown).
        - ``whole``: any inflected form of the whole phrase (from ``forms``),
          plus the exact span the blank replaced (``example_answer``), so a
          learner who reproduces the sentence's tense is always right.
        """
        if blank_mode == "particle":
            return [self.particle]
        forms = set(self.forms)
        forms.add(self.example_answer.lower())
        forms.add(self.verb)
        return sorted(forms)

    def particle_options(self, *, seed: str) -> list[str]:
        """Deterministically shuffled particle options (answer + 3 distractors).

        Only meaningful in ``particle`` blank mode. Whole-verb options are built
        by the engine (they need the global pool) via :func:`shuffle` +
        :func:`whole_distractors`. Seeded so the order is stable across the
        stateless round-trip.
        """
        pool = [self.particle, *self.distractors_particle]
        return shuffle(pool, seed=f"{seed}:{self.id}")

    def prompt(self, *, blank_mode: str, options: list[str] | None) -> dict[str, Any]:
        """Answer-free view of the item (what the client renders).

        The blank is already in ``example``. ``base`` is shown for particle mode
        (so the learner knows which verb); ``options`` is included only for
        multiple-choice play (in type mode the options would leak the answer).
        """
        view: dict[str, Any] = {
            "id": self.id,
            "blank_mode": blank_mode,
            "example": self.example,
            "definitions": list(self.definitions),
            "gloss_es": self.gloss_es,
            "difficulty": self.difficulty,
            # In particle mode we reveal the base verb (the learner supplies the
            # particle); in whole mode we don't (that would give it away).
            "base": self.base if blank_mode == "particle" else None,
        }
        if options is not None:
            view["options"] = options
        return view

    def as_state(self) -> dict[str, Any]:
        """Full serialization (includes answer material) for sealed state."""
        return {
            "id": self.id,
            "verb": self.verb,
            "particle": self.particle,
            "base": self.base,
            "definitions": list(self.definitions),
            "gloss_es": self.gloss_es,
            "example": self.example,
            "example_answer": self.example_answer,
            "forms": list(self.forms),
            "distractors_particle": list(self.distractors_particle),
            "difficulty": self.difficulty,
        }


def shuffle(pool: list[str], *, seed: str) -> list[str]:
    """Deterministic Fisher–Yates driven by a hash of *seed* (no global RNG)."""
    digest = hashlib.sha256(seed.encode()).digest()
    out = pool[:]
    for i in range(len(out) - 1, 0, -1):
        j = digest[i % len(digest)] % (i + 1)
        out[i], out[j] = out[j], out[i]
    return out


def verb_from_dict(raw: dict[str, Any]) -> Verb:
    """Build a :class:`Verb` from a stored dict (data is trusted, committed)."""
    return Verb(
        id=str(raw.get("id", "")),
        verb=str(raw.get("verb", "")),
        particle=str(raw.get("particle", "")),
        base=str(raw.get("base", "")),
        definitions=tuple(str(d) for d in raw.get("definitions", [])),
        gloss_es=(str(raw["gloss_es"]) if raw.get("gloss_es") else None),
        example=str(raw.get("example", "")),
        example_answer=str(raw.get("example_answer", "")),
        forms=tuple(str(f) for f in raw.get("forms", [])),
        distractors_particle=tuple(str(p) for p in raw.get("distractors_particle", [])),
        difficulty=str(raw.get("difficulty", "")),
    )


@dataclass(frozen=True)
class Config:
    """A validated game configuration (which difficulty band to draw from)."""

    #: ``None`` means "any difficulty" (freeplay default / daily).
    difficulty: str | None

    @property
    def pool(self) -> list[dict[str, Any]]:
        if self.difficulty is None:
            return _ALL
        filtered = [v for v in _ALL if v.get("difficulty") == self.difficulty]
        # Never hand back an empty pool just because a band is sparse.
        return filtered or _ALL


def learn_deck(difficulty: str | None = None) -> list[dict[str, Any]]:
    """Read-only vocabulary deck for Learn ("Aprender") mode.

    Returns answer-safe entries (there's nothing to hide — Learn just browses
    meanings), optionally filtered by difficulty. Unlike the exercise engine
    this exposes the full verb + all senses; the example is shown UNBLANKED so
    the learner sees the phrasal verb in a real sentence.
    """
    pool = _ALL if difficulty not in _DIFFICULTY_KEYS else [
        v for v in _ALL if v.get("difficulty") == difficulty
    ]
    deck: list[dict[str, Any]] = []
    for v in pool:
        example = str(v.get("example", ""))
        answer = str(v.get("example_answer", ""))
        # Un-blank the example so Learn shows the verb in context.
        shown = example.replace("___", answer) if answer else example
        deck.append({
            "id": v.get("id"),
            "verb": v.get("verb"),
            "particle": v.get("particle"),
            "base": v.get("base"),
            "definitions": v.get("definitions", []),
            "gloss_es": v.get("gloss_es"),
            "example": shown,
            "difficulty": v.get("difficulty"),
        })
    return deck


def default_config() -> Config:
    """Freeplay default: all difficulties mixed."""
    return Config(difficulty=None)


def resolve_config(options: dict[str, Any] | None) -> Config:
    """Turn untrusted client ``options`` into a valid :class:`Config`.

    The single place ``None``/garbage is normalized — the engine downstream
    gets a concrete ``Config`` whose pool is never empty.
    """
    if not isinstance(options, dict):
        return default_config()
    difficulty = options.get("difficulty")
    if not isinstance(difficulty, str) or difficulty not in _DIFFICULTY_KEYS:
        difficulty = None
    return Config(difficulty=difficulty)


def resolve_blank_mode(options: dict[str, Any] | None) -> str:
    """Pick the blank mode from untrusted options, defaulting to particle.

    Particle mode targets the hard part of phrasal verbs (which preposition),
    so it's the friendlier default.
    """
    if isinstance(options, dict):
        mode = options.get("blank_mode")
        if isinstance(mode, str) and mode in BLANK_MODES:
            return mode
    return "particle"


def _pool_or_raise(config: Config) -> list[dict[str, Any]]:
    pool = config.pool
    if not pool:
        raise RuntimeError("phrasal verb pool is empty (missing/empty data file)")
    return pool


def whole_distractors(answer_verb: str, *, seed: str, count: int = 3) -> list[str]:
    """Pick *count* other whole phrasal verbs as distractors for whole-verb MC.

    Deterministic by seed so the option set is stable across the round-trip.
    Drawn from the full pool, excluding the answer.
    """
    others = [v["verb"] for v in _ALL if v.get("verb") and v["verb"] != answer_verb]
    if not others:
        return []
    shuffled = shuffle(others, seed=f"wd:{seed}:{answer_verb}")
    return shuffled[:count]


def deterministic_verbs(config: Config, *, seed: int, count: int) -> list[Verb]:
    """Reproducible, non-repeating verb sequence for daily mode.

    Derives distinct indices into the stable-order pool from a hash of
    ``(seed, position)`` — same approach as the cloze daily.
    """
    pool = _pool_or_raise(config)
    n = len(pool)
    take = min(count, n)
    chosen: list[int] = []
    seen: set[int] = set()
    bump = 0
    while len(chosen) < take and bump < take * 32:
        digest = hashlib.sha256(f"{seed}:{len(chosen)}:{bump}".encode()).digest()
        idx = int.from_bytes(digest[:8], "big") % n
        bump += 1
        if idx in seen:
            continue
        seen.add(idx)
        chosen.append(idx)
    return [verb_from_dict(pool[i]) for i in chosen]


def random_verbs(config: Config, *, count: int) -> list[Verb]:
    """Draw *count* distinct random verbs from the configured pool.

    Uses ``secrets`` (no global RNG state, matching the other engines).
    """
    pool = _pool_or_raise(config)
    shuffled = pool[:]
    for i in range(len(shuffled) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        shuffled[i], shuffled[j] = shuffled[j], shuffled[i]
    take = min(count, len(shuffled))
    return [verb_from_dict(v) for v in shuffled[:take]]
