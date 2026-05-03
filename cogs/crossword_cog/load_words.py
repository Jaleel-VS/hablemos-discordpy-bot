"""Consolidate CSV word files: deduplicate and write a clean combined CSV + load to PostgreSQL."""
import asyncio
import csv
import sys
from pathlib import Path

import asyncpg

DATA_DIR = Path(__file__).resolve().parent / "data"
DB_URL = sys.argv[1] if len(sys.argv) > 1 else ""

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS crossword_words (
    id SERIAL PRIMARY KEY,
    word_es VARCHAR(12) NOT NULL,
    word_en VARCHAR(30) NOT NULL,
    clue_es TEXT NOT NULL,
    clue_en TEXT NOT NULL,
    theme VARCHAR(30) NOT NULL,
    difficulty VARCHAR(10) NOT NULL CHECK (difficulty IN ('beginner', 'advanced')),
    UNIQUE (word_es, theme)
);
CREATE INDEX IF NOT EXISTS idx_crossword_difficulty ON crossword_words (difficulty);
CREATE INDEX IF NOT EXISTS idx_crossword_theme ON crossword_words (theme);
"""


def load_csvs() -> list[tuple[str, ...]]:
    """Load all CSVs, deduplicate by word_es (keep first occurrence)."""
    seen: set[str] = set()
    rows: list[tuple[str, ...]] = []

    for f in sorted(DATA_DIR.glob("*.csv")):
        with open(f) as fh:
            for row in csv.reader(fh):
                if len(row) != 6:
                    continue
                key = row[0].lower()
                if key in seen:
                    continue
                seen.add(key)
                rows.append(tuple(row))

    return rows


async def load_to_db(rows: list[tuple[str, ...]], db_url: str) -> int:
    """Insert rows into PostgreSQL, skipping conflicts."""
    conn = await asyncpg.connect(db_url)
    try:
        await conn.execute(CREATE_TABLE)

        inserted = 0
        for word_es, word_en, clue_es, clue_en, theme, difficulty in rows:
            try:
                await conn.execute(
                    """INSERT INTO crossword_words (word_es, word_en, clue_es, clue_en, theme, difficulty)
                       VALUES ($1, $2, $3, $4, $5, $6)
                       ON CONFLICT (word_es, theme) DO NOTHING""",
                    word_es, word_en, clue_es, clue_en, theme, difficulty,
                )
                inserted += 1
            except Exception as e:
                print(f"  Skip {word_es}: {e}")

        return inserted
    finally:
        await conn.close()


def main() -> None:
    rows = load_csvs()
    print(f"Loaded {len(rows)} unique words from CSVs")

    # Write consolidated CSV
    out = DATA_DIR / "all_words.csv"
    with open(out, "w", newline="") as fh:
        writer = csv.writer(fh)
        for row in rows:
            writer.writerow(row)
    print(f"Wrote {out}")

    if not DB_URL:
        print("No DB_URL provided — skipping database load")
        return

    inserted = asyncio.run(load_to_db(rows, DB_URL))
    print(f"Inserted {inserted} rows into crossword_words")


if __name__ == "__main__":
    main()
