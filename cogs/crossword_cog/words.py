"""Word data for crossword puzzles.

Loads words from PostgreSQL (crossword_words table) at runtime.
Falls back to the consolidated CSV if the DB is unavailable.
"""
from __future__ import annotations

import csv
import logging
import random
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent / "data"


@dataclass(frozen=True)
class WordEntry:
    """A single crossword word with bilingual clues."""

    word_es: str
    word_en: str
    clue_es: str
    clue_en: str
    theme: str
    difficulty: str


def _load_csv_fallback() -> list[WordEntry]:
    """Load words from the consolidated CSV file."""
    path = DATA_DIR / "all_words.csv"
    if not path.exists():
        logger.warning("No CSV fallback found at %s", path)
        return []

    entries: list[WordEntry] = []
    with open(path) as fh:
        for row in csv.reader(fh):
            if len(row) == 6:
                entries.append(WordEntry(*row))

    logger.info("Loaded %s words from CSV fallback", len(entries))
    return entries


async def load_words_from_db(pool) -> list[WordEntry]:
    """Load all crossword words from the database."""
    try:
        rows = await pool.fetch(
            "SELECT word_es, word_en, clue_es, clue_en, theme, difficulty "
            "FROM crossword_words"
        )
        entries = [
            WordEntry(
                word_es=r["word_es"],
                word_en=r["word_en"],
                clue_es=r["clue_es"],
                clue_en=r["clue_en"],
                theme=r["theme"],
                difficulty=r["difficulty"],
            )
            for r in rows
        ]
        logger.info("Loaded %s words from database", len(entries))
        return entries
    except Exception:
        logger.exception("Failed to load words from DB, using CSV fallback")
        return _load_csv_fallback()


def pick_words(
    words: list[WordEntry], difficulty: str, count: int,
) -> list[WordEntry]:
    """Pick random words for a game, mixing themes.

    Selects at most one word per theme to ensure variety.
    Falls back to duplicates or other difficulties if needed.
    """
    by_theme: dict[str, list[WordEntry]] = {}
    for w in words:
        if w.difficulty == difficulty:
            by_theme.setdefault(w.theme, []).append(w)

    # One random word per theme
    pool: list[WordEntry] = []
    themes = list(by_theme.keys())
    random.shuffle(themes)
    for theme in themes:
        pool.append(random.choice(by_theme[theme]))
        if len(pool) >= count:
            break

    if len(pool) < count:
        # Pull more from same difficulty, allowing same themes
        remaining = [w for w in words if w.difficulty == difficulty and w not in pool]
        extra = random.sample(remaining, min(count - len(pool), len(remaining)))
        pool.extend(extra)

    if len(pool) < count:
        # Still short — pull from other difficulty
        remaining = [w for w in words if w not in pool]
        extra = random.sample(remaining, min(count - len(pool), len(remaining)))
        pool.extend(extra)

    return random.sample(pool, min(count, len(pool)))
