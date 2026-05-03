"""Generate crossword words via Amazon Bedrock (Claude Haiku 3.5).

Usage:
    python scripts/generate_crossword_words.py [--profile PROFILE] [--dry-run] [--db DATABASE_URL]

Generates words for themes × difficulties that are below the target count,
validates against existing words, and writes to CSV + optionally loads to DB.
"""
import argparse
import asyncio
import csv
import json
import re
import sys
import unicodedata
from pathlib import Path

import boto3

DATA_DIR = Path(__file__).resolve().parent.parent / "cogs" / "crossword_cog" / "data"
OUTPUT_CSV = DATA_DIR / "generated_batch.csv"

MODEL_ID = "us.anthropic.claude-3-5-haiku-20241022-v1:0"
TARGET_PER_THEME_DIFF = 25  # aim for at least 25 words per theme×difficulty
BATCH_SIZE = 20  # words per API call

# All existing themes
THEMES = [
    "adjetivos", "animales", "apariencia", "arte", "aves", "bebidas",
    "calendario", "casa", "ciencia", "ciudad", "clima", "cocinar",
    "colores", "comida", "compras", "comunicacion", "cuerpo", "cultura",
    "deportes", "emociones", "escuela", "espacio", "familia", "frutas",
    "geografia", "herramientas", "insectos", "internet", "jardin", "jerga",
    "limpieza", "lugares", "marinos", "matematicas", "materiales",
    "modismos", "musica", "naturaleza", "numeros", "objetos",
    "pasatiempos", "personalidad", "profesiones", "relaciones", "religion",
    "restaurante", "ropa", "salud", "sentimientos", "tecnologia", "tiempo",
    "trabajo", "transporte", "verbos", "verduras", "viajes",
]

DIFFICULTIES = ["beginner", "advanced"]


def load_existing() -> tuple[set[str], dict[tuple[str, str], int]]:
    """Load existing words from all_words.csv + generated_batch.csv."""
    existing: set[str] = set()
    counts: dict[tuple[str, str], int] = {}
    for fname in ("all_words.csv", "generated_batch.csv"):
        path = DATA_DIR / fname
        if not path.exists():
            continue
        with open(path) as f:
            for row in csv.reader(f):
                if len(row) == 6:
                    existing.add(row[0].lower())
                    key = (row[4], row[5])
                    counts[key] = counts.get(key, 0) + 1
    return existing, counts


def build_prompt(theme: str, difficulty: str, existing_words: list[str], count: int) -> str:
    diff_desc = (
        "common, everyday vocabulary (A1-A2 level)" if difficulty == "beginner"
        else "less common, intermediate-advanced vocabulary (B1-B2 level)"
    )
    exclude = ", ".join(existing_words[:50]) if existing_words else "none"

    return f"""Generate exactly {count} Spanish crossword words for theme "{theme}" at {difficulty} level ({diff_desc}).

Rules:
- word_es: single Spanish word, max 9 characters, no spaces, no hyphens
- word_en: English translation (can be multi-word)
- clue_es: short Spanish clue (1 sentence, ≤80 chars)
- clue_en: short English clue (1 sentence, ≤80 chars)
- Clues should be descriptive hints, NOT just translations
- All clues must be grammatically correct
- Do NOT repeat these existing words: {exclude}

Output ONLY a JSON array, no markdown, no explanation:
[{{"word_es":"gato","word_en":"cat","clue_es":"Felino doméstico que ronronea","clue_en":"Domestic feline that purrs"}}]"""


def normalize(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text.strip().lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def validate_word(entry: dict, existing: set[str]) -> str | None:
    """Return error string or None if valid."""
    w = entry.get("word_es", "").strip()
    if not w:
        return "empty word_es"
    if len(w) > 9:
        return f"word_es too long: {w} ({len(w)})"
    if " " in w or "-" in w:
        return f"word_es has space/hyphen: {w}"
    if normalize(w) in existing:
        return f"duplicate: {w}"
    for field in ("word_en", "clue_es", "clue_en"):
        if not entry.get(field, "").strip():
            return f"empty {field}"
    return None


def call_bedrock(client, prompt: str) -> list[dict]:
    """Call Bedrock Converse API and parse JSON response."""
    resp = client.converse(
        modelId=MODEL_ID,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 4096, "temperature": 0.8},
    )
    text = resp["output"]["message"]["content"][0]["text"].strip()

    # Extract JSON array from response (handle markdown wrapping)
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        print(f"  ⚠️  No JSON array found in response")
        return []

    try:
        return json.loads(match.group())
    except json.JSONDecodeError as e:
        print(f"  ⚠️  JSON parse error: {e}")
        return []


def main():
    parser = argparse.ArgumentParser(description="Generate crossword words via Bedrock")
    parser.add_argument("--profile", default="Jaleel", help="AWS profile name")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without calling API")
    parser.add_argument("--db", default="", help="DATABASE_URL to load into PostgreSQL")
    parser.add_argument("--target", type=int, default=TARGET_PER_THEME_DIFF)
    args = parser.parse_args()

    existing, counts = load_existing()
    print(f"Existing: {len(existing)} unique words across {len(counts)} theme×difficulty combos\n")

    # Build generation plan
    plan: list[tuple[str, str, int]] = []
    for theme in THEMES:
        for diff in DIFFICULTIES:
            current = counts.get((theme, diff), 0)
            needed = max(0, args.target - current)
            if needed > 0:
                plan.append((theme, diff, needed))

    total_needed = sum(n for _, _, n in plan)
    print(f"Generation plan: {len(plan)} batches, ~{total_needed} words needed\n")

    for theme, diff, needed in plan:
        current = counts.get((theme, diff), 0)
        print(f"  {theme:20s} {diff:10s}  {current:2d} → {args.target}  (+{needed})")

    if args.dry_run:
        print("\n--dry-run: stopping here")
        return

    if not plan:
        print("Nothing to generate — all themes at target!")
        return

    print(f"\nGenerating with {MODEL_ID} (profile: {args.profile})...\n")

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    client = session.client("bedrock-runtime")

    all_new: list[tuple[str, ...]] = []
    consecutive_errors = 0

    # Open output file for incremental writing
    csv_file = open(OUTPUT_CSV, "a" if OUTPUT_CSV.exists() else "w", newline="")
    writer = csv.writer(csv_file)

    for theme, diff, needed in plan:
        if consecutive_errors >= 3:
            print(f"\n❌ 3 consecutive API errors — aborting. Fix the issue and re-run.")
            break

        # Get existing words for this theme to exclude
        theme_existing = []
        path = DATA_DIR / "all_words.csv"
        if path.exists():
            with open(path) as f:
                for row in csv.reader(f):
                    if len(row) == 6 and row[4] == theme:
                        theme_existing.append(row[0])

        prompt = build_prompt(theme, diff, theme_existing, min(needed, BATCH_SIZE))
        print(f"  {theme}/{diff} — requesting {min(needed, BATCH_SIZE)} words...", end=" ", flush=True)

        try:
            entries = call_bedrock(client, prompt)
            consecutive_errors = 0
        except Exception as e:
            print(f"❌ API error: {e}")
            consecutive_errors += 1
            continue

        valid = 0
        for entry in entries:
            err = validate_word(entry, existing)
            if err:
                continue
            word_es = entry["word_es"].strip().lower()
            row = (
                word_es,
                entry["word_en"].strip(),
                entry["clue_es"].strip(),
                entry["clue_en"].strip(),
                theme,
                diff,
            )
            all_new.append(row)
            writer.writerow(row)
            existing.add(normalize(word_es))
            valid += 1

        csv_file.flush()
        print(f"✅ {valid}/{len(entries)} valid")

    csv_file.close()

    # Summary
    if all_new:
        print(f"\n✅ Wrote {len(all_new)} words to {OUTPUT_CSV}")

        # Optionally load to DB
        if args.db:
            print(f"\nLoading to database...")
            # Reuse the existing load_words.py logic
            sys.path.insert(0, str(DATA_DIR.parent))
            from load_words import load_to_db
            inserted = asyncio.run(load_to_db(all_new, args.db))
            print(f"✅ Inserted {inserted} rows")
    else:
        print("\n⚠️  No valid words generated")


if __name__ == "__main__":
    main()
