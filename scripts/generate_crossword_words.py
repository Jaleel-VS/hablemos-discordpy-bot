"""Generate crossword words via Amazon Bedrock (Claude Haiku 3.5).

Usage:
    python scripts/generate_crossword_words.py [--profile PROFILE] [--dry-run] [--db DATABASE_URL]
    python scripts/generate_crossword_words.py --themes medicina,leyes --difficulties advanced
    python scripts/generate_crossword_words.py --target 70 --batch-size 25

Generates words for themes × difficulties that are below the target count,
validates against existing words, and appends to generated_batch.csv.
Run load_words.py afterwards to consolidate into all_words.csv + DB.
"""

import argparse
import csv
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

import boto3

DATA_DIR = Path(__file__).resolve().parent.parent / "cogs" / "crossword_cog" / "data"
OUTPUT_CSV = DATA_DIR / "generated_batch.csv"

MODEL_ID = "us.anthropic.claude-3-5-haiku-20241022-v1:0"
DEFAULT_TARGET = 70
DEFAULT_BATCH_SIZE = 25

THEMES = [
    # Existing 56
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
    # New 18
    "medicina", "leyes", "moda", "arquitectura", "filosofia", "economia",
    "militar", "mitologia", "astronomia", "quimica", "botanica", "zoologia",
    "gastronomia", "fotografia", "cine", "teatro", "danza", "literatura",
]

DIFFICULTIES = ["beginner", "advanced"]


def normalize(text: str) -> str:
    """Strip accents and lowercase for comparison."""
    nfkd = unicodedata.normalize("NFKD", text.strip().lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def load_existing() -> tuple[set[str], dict[tuple[str, str], int]]:
    """Load existing words from all CSVs in data dir."""
    existing: set[str] = set()
    counts: dict[tuple[str, str], int] = {}
    for path in DATA_DIR.glob("*.csv"):
        if not path.exists():
            continue
        with open(path) as f:
            for row in csv.reader(f):
                if len(row) == 6:
                    existing.add(normalize(row[0]))
                    key = (row[4], row[5])
                    counts[key] = counts.get(key, 0) + 1
    return existing, counts


def get_theme_words(theme: str) -> list[str]:
    """Get existing word_es values for a theme (for exclusion in prompt)."""
    words: list[str] = []
    for path in DATA_DIR.glob("*.csv"):
        with open(path) as f:
            for row in csv.reader(f):
                if len(row) == 6 and row[4] == theme:
                    words.append(row[0])
    return words


def build_prompt(theme: str, difficulty: str, exclude_words: list[str], count: int) -> str:
    diff_desc = (
        "common, everyday vocabulary (A1-A2 level)" if difficulty == "beginner"
        else "less common, intermediate-advanced vocabulary (B1-B2 level)"
    )
    # Show up to 80 existing words to avoid duplicates
    exclude = ", ".join(exclude_words[:80]) if exclude_words else "none"

    return f"""Generate exactly {count} Spanish crossword words for theme "{theme}" at {difficulty} level ({diff_desc}).

HARD RULES — every word must satisfy ALL of these:
1. word_es: a single real Spanish word, lowercase, max 12 characters, no spaces, no hyphens, no accents needed (stripped for crossword grid)
2. word_en: accurate English translation (single word preferred, multi-word OK if needed)
3. clue_es: Spanish hint, 1 sentence, ≤80 characters. Must NOT contain the answer word (word_es).
4. clue_en: English hint, 1 sentence, ≤80 characters. Must NOT contain the answer word (word_en).
5. word_es must NOT be the same as word_en (even after removing accents). Reject cognates like "tsunami", "pizza", "yoga".
6. Clues should be descriptive definitions or hints, NOT just translations of each other.
7. Every word must be a real, commonly recognized word — no truncated, invented, or nonsense words.

Do NOT include any of these existing words: {exclude}

Output ONLY a JSON array with no markdown fences, no explanation:
[{{"word_es":"gato","word_en":"cat","clue_es":"Felino doméstico que ronronea","clue_en":"Domestic feline that purrs"}}]"""


def _looks_truncated(word: str) -> bool:
    """Heuristic: flag words that end mid-syllable (likely truncated by the LLM)."""
    # Spanish words almost never end with these consonant clusters
    bad_endings = (
        "cr", "gr", "pr", "tr", "br", "dr", "fr",
        "cl", "gl", "pl", "tl", "bl", "fl",
        "ct", "pt", "gn", "mn", "ps", "pn",
        "sf", "sg", "sl", "sm", "sn", "sp", "sq", "sr", "st", "sv",
    )
    if word.endswith(bad_endings):
        return True
    # Fragments of common suffixes that suggest the word was cut short
    # e.g. "tonalida" (missing -d), "oceanogra" (missing -fo/-fía)
    truncation_fragments = (
        "acio", "acio", "ogra", "osfe", "ecno", "elac",
        "spec", "ernag", "amr", "opag", "ipiel",
    )
    if any(word.endswith(frag) for frag in truncation_fragments):
        return True
    # Valid Spanish word-final consonants: n, s, r, l, d, z, j, x (rare but real)
    return len(word) >= 6 and word[-1] not in "aeiouáéíóúünsrldz"


def validate_word(entry: dict, existing: set[str]) -> str | None:
    """Return error string or None if valid."""
    w_es = entry.get("word_es", "").strip().lower()
    w_en = entry.get("word_en", "").strip()

    if not w_es:
        return "empty word_es"
    if len(w_es) > 12:
        return f"too long ({len(w_es)}): {w_es}"
    if " " in w_es or "-" in w_es:
        return f"space/hyphen: {w_es}"
    if not re.match(r"^[a-záéíóúüñ]+$", w_es):
        return f"invalid chars: {w_es}"
    if normalize(w_es) in existing:
        return f"duplicate: {w_es}"
    # Reject if es == en after normalization (cognates)
    if normalize(w_es) == normalize(w_en):
        return f"cognate: {w_es}={w_en}"
    if _looks_truncated(w_es):
        return f"truncated: {w_es}"

    for field in ("word_en", "clue_es", "clue_en"):
        val = entry.get(field, "").strip()
        if not val:
            return f"empty {field}"

    c_es = entry.get("clue_es", "").strip()
    c_en = entry.get("clue_en", "").strip()

    # Clue must not contain the answer
    if w_es in c_es.lower():
        return f"clue_es contains '{w_es}'"
    if w_en.lower() in c_en.lower():
        return f"clue_en contains '{w_en}'"

    # Clue length
    if len(c_es) > 80:
        return f"clue_es too long ({len(c_es)})"
    if len(c_en) > 80:
        return f"clue_en too long ({len(c_en)})"

    return None


def call_bedrock(client, prompt: str) -> list[dict]:
    """Call Bedrock Converse API and parse JSON response."""
    resp = client.converse(
        modelId=MODEL_ID,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 4096, "temperature": 0.8},
    )
    text = resp["output"]["message"]["content"][0]["text"].strip()

    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        return []

    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return []


def main():
    parser = argparse.ArgumentParser(description="Generate crossword words via Bedrock")
    parser.add_argument("--profile", default="Jaleel")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--target", type=int, default=DEFAULT_TARGET)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--themes", default="", help="Comma-separated theme filter")
    parser.add_argument("--difficulties", default="", help="Comma-separated difficulty filter")
    parser.add_argument("--max-batches", type=int, default=0, help="Stop after N batches (0=unlimited)")
    parser.add_argument("--clear-batch", action="store_true", help="Clear generated_batch.csv before starting")
    args = parser.parse_args()

    if args.clear_batch and OUTPUT_CSV.exists():
        OUTPUT_CSV.unlink()
        print(f"Cleared {OUTPUT_CSV}\n")

    existing, counts = load_existing()
    print(f"Existing: {len(existing)} unique words\n")

    # Filter themes/difficulties if specified
    themes = [t.strip() for t in args.themes.split(",") if t.strip()] if args.themes else THEMES
    diffs = [d.strip() for d in args.difficulties.split(",") if d.strip()] if args.difficulties else DIFFICULTIES

    # Build generation plan: (theme, difficulty, needed)
    plan: list[tuple[str, str, int]] = []
    for theme in themes:
        for diff in diffs:
            current = counts.get((theme, diff), 0)
            needed = max(0, args.target - current)
            if needed > 0:
                plan.append((theme, diff, needed))

    # Sort: most-needed first (new themes get priority)
    plan.sort(key=lambda x: -x[2])

    total_needed = sum(n for _, _, n in plan)
    est_batches = sum((n + args.batch_size - 1) // args.batch_size for _, _, n in plan)
    print(f"Plan: {len(plan)} theme×diff combos, ~{total_needed} words, ~{est_batches} API calls\n")

    for theme, diff, needed in plan[:20]:
        current = counts.get((theme, diff), 0)
        print(f"  {theme:20s} {diff:10s}  {current:3d} → {args.target}  (+{needed})")
    if len(plan) > 20:
        print(f"  ... and {len(plan) - 20} more")

    if args.dry_run:
        print("\n--dry-run: stopping here")
        return

    if not plan:
        print("Nothing to generate — all themes at target!")
        return

    print(f"\nGenerating with {MODEL_ID} (profile: {args.profile})...\n")

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    client = session.client("bedrock-runtime")

    total_generated = 0
    total_rejected = 0
    batch_count = 0
    consecutive_errors = 0

    csv_file = open(OUTPUT_CSV, "a", newline="")
    writer = csv.writer(csv_file)

    try:
        for theme, diff, needed in plan:
            remaining = needed
            theme_words = get_theme_words(theme)

            while remaining > 0:
                if consecutive_errors >= 3:
                    print("\n❌ 3 consecutive errors — aborting.")
                    sys.exit(1)

                if args.max_batches and batch_count >= args.max_batches:
                    print(f"\n⏹  Reached --max-batches {args.max_batches}")
                    csv_file.close()
                    _print_summary(total_generated, total_rejected)
                    return

                request_count = min(remaining, args.batch_size)
                prompt = build_prompt(theme, diff, theme_words, request_count)
                label = f"{theme}/{diff}"
                print(f"  [{batch_count + 1}] {label:35s} requesting {request_count:2d}...", end=" ", flush=True)

                try:
                    entries = call_bedrock(client, prompt)
                    consecutive_errors = 0
                except Exception as e:
                    print(f"❌ {e}")
                    consecutive_errors += 1
                    time.sleep(2)
                    continue

                valid = 0
                reject_reasons: dict[str, int] = {}
                for entry in entries:
                    entry["word_es"] = entry.get("word_es", "").strip().lower()
                    err = validate_word(entry, existing)
                    if err:
                        total_rejected += 1
                        reason = err.split(":")[0].strip()
                        reject_reasons[reason] = reject_reasons.get(reason, 0) + 1
                        continue

                    row = (
                        entry["word_es"],
                        entry["word_en"].strip(),
                        entry["clue_es"].strip(),
                        entry["clue_en"].strip(),
                        theme,
                        diff,
                    )
                    writer.writerow(row)
                    existing.add(normalize(entry["word_es"]))
                    theme_words.append(entry["word_es"])
                    valid += 1

                csv_file.flush()
                total_generated += valid
                batch_count += 1
                remaining -= request_count
                rejects = "  ".join(f"{k}={v}" for k, v in reject_reasons.items()) if reject_reasons else ""
                print(f"✅ {valid}/{len(entries)} valid  (total: {total_generated})" + (f"  [{rejects}]" if rejects else ""))

                # Brief pause to avoid throttling
                time.sleep(0.5)

    except KeyboardInterrupt:
        print("\n\n⏹  Interrupted by user")
    finally:
        csv_file.close()

    _print_summary(total_generated, total_rejected)


def _print_summary(generated: int, rejected: int):
    print(f"\n{'=' * 50}")
    print(f"Generated: {generated}  |  Rejected: {rejected}")
    if OUTPUT_CSV.exists():
        with open(OUTPUT_CSV) as f:
            batch_total = sum(1 for _ in csv.reader(f))
        print(f"Batch file: {OUTPUT_CSV} ({batch_total} rows)")
    print("\nNext steps:")
    print(f"  1. Review: head -20 {OUTPUT_CSV}")
    print("  2. Consolidate: .venv/bin/python cogs/crossword_cog/load_words.py")
    print("  3. Load to DB: .venv/bin/python cogs/crossword_cog/load_words.py \"$DATABASE_URL\"")


if __name__ == "__main__":
    main()
