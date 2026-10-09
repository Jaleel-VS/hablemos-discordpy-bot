"""Word-list loading for Spanish Wordle.

Two lists (both normalized, 5 letters, ñ preserved):
* **answers** — curated common words; the daily secret is drawn from here.
* **free_answers** — ANSWERS minus retired (obscure/low-utility) words;
  freeplay draws from this subset so learners see useful vocabulary.
* **guesses** — permissive superset accepted as a guess. Includes every answer.

Loaded once at import into module-level immutables. The answer list order is
stable (sorted at build time) so the daily-index mapping is reproducible
across restarts and deploys.
"""
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _load(name: str) -> list[str]:
    path = _DATA_DIR / name
    with path.open(encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


# Stable, sorted order — do not re-sort or shuffle; the daily index depends on it.
ANSWERS: tuple[str, ...] = tuple(_load("wordle_answers.txt"))
_GUESS_SET: frozenset[str] = frozenset(_load("wordle_guesses.txt"))

# Words retired from freeplay because they are obscure or low-utility for
# A1–B1 learners. The daily pool keeps ANSWERS unchanged (byte-stable).
_RETIRED: frozenset[str] = frozenset(_load("wordle_answers_retired.txt"))
FREE_ANSWERS: tuple[str, ...] = tuple(w for w in ANSWERS if w not in _RETIRED)


def is_valid_guess(normalized: str) -> bool:
    """Whether a normalized word is an accepted guess."""
    return normalized in _GUESS_SET


def answer_count() -> int:
    return len(ANSWERS)


def free_answer_count() -> int:
    return len(FREE_ANSWERS)
