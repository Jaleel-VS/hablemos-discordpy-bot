"""Card data + selection helpers for the cloze game.

Loads the precomputed ``cloze_sentences.json`` (built offline by
``scripts/generate_cloze_sentences.py`` via Bedrock/Haiku) exactly once at
import. The runtime never calls an LLM — it just reads this JSON, the same rule
the conjugation game follows with its paradigm data.

Everything the engine needs to *pose a card* and *know the answer* lives here:
the card pool keyed by target language, the difficulty catalog, and the pickers
(deterministic for daily, random for freeplay).

A card::

    {
      "id": "es-0001",
      "target": "es",              # language of the blanked word
      "cloze": "El ___ duerme.",   # target sentence with a single ___ blank
      "answer": "gato",            # the blanked word (canonical form)
      "context": "The cat sleeps.",# the OTHER language, full sentence
      "distractors": ["perro", "pájaro", "ratón"],
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

_DATA = Path(__file__).resolve().parent.parent / "data" / "cloze_sentences.json"

_raw: dict[str, Any] = json.loads(_DATA.read_text(encoding="utf-8")) if _DATA.exists() else {}

#: difficulty key -> display label ("beginner" -> "Principiante").
DIFFICULTIES: dict[str, str] = _raw.get("difficulties", {
    "beginner": "Principiante",
    "intermediate": "Intermedio",
    "advanced": "Avanzado",
})

#: All cards, in file order.
_ALL_CARDS: list[dict[str, Any]] = _raw.get("cards", [])

#: Valid target languages present in the data (e.g. {"es", "en"}).
TARGETS: list[str] = sorted({c["target"] for c in _ALL_CARDS if "target" in c})

#: target -> ordered list of that deck's cards (stable order for daily indexing).
_BY_TARGET: dict[str, list[dict[str, Any]]] = {
    t: [c for c in _ALL_CARDS if c.get("target") == t] for t in TARGETS
}

_DIFFICULTY_KEYS = set(DIFFICULTIES)
_DEFAULT_TARGET = "es" if "es" in TARGETS else (TARGETS[0] if TARGETS else "es")



@dataclass(frozen=True)
class Card:
    """One cloze prompt and its authoritative answer.

    ``answer`` stays server-side (sealed) and is never placed in a client view
    until the card has been answered.
    """

    id: str
    target: str
    cloze: str
    answer: str
    context: str
    distractors: tuple[str, ...]
    difficulty: str

    def options(self, *, seed: str) -> list[str]:
        """Deterministically shuffled multiple-choice options (answer + 3).

        Seeded so the same card in the same run always presents options in the
        same order (the order round-trips in sealed state, so grading by index
        is stable). Uses a hash-derived permutation — no global RNG state.
        """
        pool = [self.answer, *self.distractors]
        digest = hashlib.sha256(f"{seed}:{self.id}".encode()).digest()
        # Fisher–Yates driven by successive digest bytes (pool is tiny: 4).
        out = pool[:]
        for i in range(len(out) - 1, 0, -1):
            j = digest[i % len(digest)] % (i + 1)
            out[i], out[j] = out[j], out[i]
        return out

    def prompt(self, *, seed: str, include_options: bool = True) -> dict[str, Any]:
        """Answer-free view of the card (what the client renders).

        ``options`` (the shuffled answer + distractors) is included only for
        multiple-choice play. In type-in mode the options *contain the answer*,
        so emitting them would hand the client the answer outright — they are
        omitted there.
        """
        view: dict[str, Any] = {
            "id": self.id,
            "target": self.target,
            "cloze": self.cloze,
            "context": self.context,
            "difficulty": self.difficulty,
        }
        if include_options:
            view["options"] = self.options(seed=seed)
        return view

    def as_state(self) -> dict[str, Any]:
        """Full serialization (includes the answer) for sealed state."""
        return {
            "id": self.id,
            "target": self.target,
            "cloze": self.cloze,
            "answer": self.answer,
            "context": self.context,
            "distractors": list(self.distractors),
            "difficulty": self.difficulty,
        }


def _card_from_dict(raw: dict[str, Any]) -> Card:
    """Build a :class:`Card` from a stored dict (data is trusted, committed)."""
    return Card(
        id=str(raw.get("id", "")),
        target=str(raw.get("target", "")),
        cloze=str(raw.get("cloze", "")),
        answer=str(raw.get("answer", "")),
        context=str(raw.get("context", "")),
        distractors=tuple(str(d) for d in raw.get("distractors", [])),
        difficulty=str(raw.get("difficulty", "")),
    )


@dataclass(frozen=True)
class Config:
    """A validated game configuration (which deck + difficulty to draw from)."""

    target: str
    #: ``None`` means "any difficulty" (freeplay default / daily).
    difficulty: str | None

    @property
    def pool(self) -> list[dict[str, Any]]:
        cards = _BY_TARGET.get(self.target, [])
        if self.difficulty is None:
            return cards
        filtered = [c for c in cards if c.get("difficulty") == self.difficulty]
        # Never hand back an empty pool just because a difficulty is sparse.
        return filtered or cards


def default_config() -> Config:
    """Freeplay defaults: the Spanish deck, all difficulties mixed."""
    return Config(target=_DEFAULT_TARGET, difficulty=None)


def resolve_config(options: dict[str, Any] | None) -> Config:
    """Turn untrusted client ``options`` into a valid :class:`Config`.

    Every field falls back to a default when missing or invalid, so a hostile
    or partial payload can never produce an empty pool. This is the single
    place ``None``/garbage is normalized — the engine downstream gets a concrete
    ``Config`` it can trust.
    """
    base = default_config()
    if not isinstance(options, dict):
        return base

    target = options.get("target")
    if not isinstance(target, str) or target not in TARGETS or not _BY_TARGET.get(target):
        target = base.target

    difficulty = options.get("difficulty")
    if not isinstance(difficulty, str) or difficulty not in _DIFFICULTY_KEYS:
        difficulty = None  # "any"

    return Config(target=target, difficulty=difficulty)


def daily_config() -> Config:
    """Fixed daily config: the Spanish deck, all difficulties (mixed run)."""
    return Config(target=_DEFAULT_TARGET, difficulty=None)


def _pool_or_raise(config: Config) -> list[dict[str, Any]]:
    pool = config.pool
    if not pool:
        raise RuntimeError("cloze card pool is empty (missing/empty data file)")
    return pool


def deterministic_cards(config: Config, *, seed: int, count: int) -> list[Card]:
    """Reproducible, non-repeating card sequence for daily mode.

    Derives ``count`` distinct indices into the (stable-order) pool from a hash
    of ``(seed, position)``, so the daily round yields the same ordered cards
    for everyone without storing any RNG state across the stateless round-trip.
    """
    pool = _pool_or_raise(config)
    n = len(pool)
    take = min(count, n)
    chosen: list[int] = []
    seen: set[int] = set()
    bump = 0
    # Walk deterministically, skipping collisions, until we have ``take`` unique
    # indices (bounded — the pool is far larger than a round).
    while len(chosen) < take and bump < take * 32:
        digest = hashlib.sha256(f"{seed}:{len(chosen)}:{bump}".encode()).digest()
        idx = int.from_bytes(digest[:8], "big") % n
        bump += 1
        if idx in seen:
            continue
        seen.add(idx)
        chosen.append(idx)
    return [_card_from_dict(pool[i]) for i in chosen]


def random_cards(config: Config, *, count: int, avoid_ids: set[str] | None = None) -> list[Card]:
    """Draw ``count`` distinct random cards from the configured pool.

    Uses ``secrets`` (no global RNG state, matching the other engines). Falls
    back gracefully when the pool is smaller than ``count``.
    """
    pool = _pool_or_raise(config)
    avoid = avoid_ids or set()
    candidates = [c for c in pool if c.get("id") not in avoid] or pool
    take = min(count, len(candidates))
    # Sample without replacement via a shuffled copy (pool sizes are modest).
    shuffled = candidates[:]
    for i in range(len(shuffled) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        shuffled[i], shuffled[j] = shuffled[j], shuffled[i]
    return [_card_from_dict(c) for c in shuffled[:take]]
