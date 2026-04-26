"""
CEFR Vocabulary Generator — generates leveled word lists with cloze sentences via Bedrock Claude.

Usage:
    python generate.py spanish A 50    # Generate 50 A-level Spanish words
    python generate.py english B 25    # Generate 25 B-level English words
    python generate.py export          # Export all words to JSON for bot import
    python generate.py stats           # Show generation stats

State is tracked in vocab.db (SQLite) to avoid duplicates across runs.
"""
import json
import sqlite3
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import boto3

DB_PATH = Path(__file__).parent / "vocab.db"
EXPORT_PATH = Path(__file__).parent / "vocab_export.json"

BEDROCK_MODEL = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
BEDROCK_REGION = "us-west-2"
BATCH_SIZE = 25  # words per API call

_print_lock = threading.Lock()


def _log(level: str, msg: str):
    """Thread-safe print with level prefix."""
    with _print_lock:
        print(f"[{level}] {msg}")

LEVEL_DESCRIPTIONS = {
    "A": (
        "Beginner (CEFR A1-A2). Basic survival vocabulary: greetings, numbers, colors, "
        "family, food, daily routines, simple descriptions. Use only present tense and "
        "simple past in sentences. Short sentences (5-10 words)."
    ),
    "B": (
        "Intermediate (CEFR B1-B2). Everyday and professional vocabulary: travel, work, "
        "opinions, health, media, abstract concepts. Can use conditionals, subjunctive, "
        "compound tenses. Medium sentences (8-15 words)."
    ),
    "C": (
        "Advanced (CEFR C1-C2). Sophisticated vocabulary: academic, literary, idiomatic "
        "expressions, nuanced synonyms, formal register. Complex grammar including passive "
        "voice, advanced subjunctive, relative clauses. Longer sentences (12-20 words)."
    ),
}

TOPICS = {
    "A": [
        "greetings & introductions", "numbers & time", "family & people",
        "food & drink", "colors & descriptions", "daily routines",
        "house & home", "weather", "body & health basics", "shopping basics",
        "clothing & appearance", "animals", "school & classroom",
        "emotions (basic)", "hobbies & sports", "directions & places",
        "jobs & occupations", "days, months & seasons", "furniture & objects",
        "verbs of movement",
    ],
    "B": [
        "travel & transport", "work & career", "health & medicine",
        "media & technology", "environment & nature", "emotions & opinions",
        "education", "culture & entertainment", "relationships", "news & current events",
        "cooking & recipes", "sports & competition", "money & banking",
        "housing & real estate", "personality & character", "social media & internet",
        "government & civic life", "celebrations & traditions", "crime & safety",
        "science basics",
    ],
    "C": [
        "politics & society", "science & research", "law & justice",
        "economics & finance", "philosophy & ethics", "literature & arts",
        "idiomatic expressions", "formal correspondence", "debate & argumentation",
        "academic writing", "psychology & behavior", "diplomacy & international relations",
        "medicine & anatomy", "architecture & urban planning", "linguistics & language",
        "mythology & history", "business strategy", "environmental policy",
        "journalism & media criticism", "abstract concepts & reasoning",
    ],
}


def init_db() -> sqlite3.Connection:
    """Initialize SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word TEXT NOT NULL,
            translation TEXT NOT NULL,
            language TEXT NOT NULL,
            level TEXT NOT NULL,
            topic TEXT,
            sentence TEXT NOT NULL,
            sentence_with_blank TEXT NOT NULL,
            sentence_translation TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(word, language)
        )
    """)
    conn.commit()
    return conn


def get_existing_words(conn: sqlite3.Connection, language: str, level: str) -> list[str]:
    """Get all existing words for a language/level combo."""
    rows = conn.execute(
        "SELECT word FROM words WHERE language = ? AND level = ?",
        (language, level),
    ).fetchall()
    return [r[0] for r in rows]


def get_all_existing_words(conn: sqlite3.Connection, language: str) -> list[str]:
    """Get all existing words for a language (any level)."""
    rows = conn.execute(
        "SELECT word FROM words WHERE language = ?", (language,)
    ).fetchall()
    return [r[0] for r in rows]


def call_bedrock(prompt: str) -> str:
    """Call Bedrock Claude and return the response text."""
    # Refresh short-lived ADA credentials before each call
    subprocess.run(
        ["ada", "credentials", "update", "--profile", "Jaleel", "--once"],
        capture_output=True,
    )
    session = boto3.Session(profile_name="Jaleel")
    client = session.client("bedrock-runtime", region_name=BEDROCK_REGION)
    response = client.converse(
        modelId=BEDROCK_MODEL,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 4096},
    )
    return response["output"]["message"]["content"][0]["text"]


def build_prompt(language: str, level: str, count: int, existing: list[str], topic: str) -> str:
    """Build the generation prompt."""
    target_lang = "Spanish" if language == "spanish" else "English"
    other_lang = "English" if language == "spanish" else "Spanish"
    level_desc = LEVEL_DESCRIPTIONS[level]

    exclude_section = ""
    if existing:
        # Only show last 200 to keep prompt manageable
        sample = existing[-200:]
        exclude_section = f"\n\nDO NOT include any of these words (already generated):\n{', '.join(sample)}\n"

    return f"""Generate exactly {count} {target_lang} vocabulary words at level {level} ({level_desc}).

Topic focus: {topic}
{exclude_section}
For each word, provide:
1. The {target_lang} word (infinitive for verbs, singular for nouns)
2. The {other_lang} translation of the word
3. A natural {target_lang} sentence using the word (appropriate for this CEFR level)
4. The same sentence with the target word replaced by "___"
5. A natural {other_lang} translation of the full sentence

Return ONLY a JSON array, no markdown, no explanation. Each element:
{{"word": "...", "translation": "...", "sentence": "...", "sentence_with_blank": "...", "sentence_translation": "..."}}

Rules:
- Words must be useful, common vocabulary for this level — not obscure
- Sentences must use grammar appropriate for the level
- The blank must replace exactly the target word
- No proper nouns, no slang unless level C
- Verbs in infinitive form as the "word", but conjugated naturally in the sentence"""


def parse_response(text: str) -> list[dict]:
    """Parse the JSON response from Claude."""
    # Strip markdown fences if present
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1]
    if cleaned.endswith("```"):
        cleaned = cleaned.rsplit("```", 1)[0]
    cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
        if not isinstance(data, list):
            print(f"  ⚠ Response is not a list: {type(data)}")
            return []
        return data
    except json.JSONDecodeError as e:
        print(f"  ⚠ JSON parse error: {e}")
        print(f"  Raw response: {cleaned[:200]}...")
        return []


def save_words(conn: sqlite3.Connection, words: list[dict], language: str, level: str, topic: str) -> int:
    """Save words to the database, skipping duplicates. Returns count saved."""
    saved = 0
    for w in words:
        try:
            before = conn.total_changes
            conn.execute(
                "INSERT OR IGNORE INTO words (word, translation, language, level, topic, sentence, sentence_with_blank, sentence_translation) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (w["word"].lower().strip(), w["translation"], language, level, topic,
                 w["sentence"], w["sentence_with_blank"], w.get("sentence_translation", "")),
            )
            if conn.total_changes > before:
                saved += 1
        except (KeyError, sqlite3.Error) as e:
            print(f"  ⚠ Skipping bad entry: {e}")
    conn.commit()
    return saved


def generate(language: str, level: str, target_count: int):
    """Generate vocabulary words."""
    conn = init_db()
    topics = TOPICS[level]
    existing = get_all_existing_words(conn, language)
    level_existing = get_existing_words(conn, language, level)

    _log(level, f"🎯 Generating {target_count} {language} words (have {len(level_existing)})")

    generated = 0
    topic_idx = len(level_existing) % len(topics)
    cycle_new = 0

    while generated < target_count:
        topic = topics[topic_idx % len(topics)]
        batch = min(BATCH_SIZE, target_count - generated)

        _log(level, f"📝 {topic} ({batch} words)")
        prompt = build_prompt(language, level, batch, existing, topic)

        try:
            raw = call_bedrock(prompt)
            words = parse_response(raw)

            saved = save_words(conn, words, language, level, topic)
            _log(level, f"   ✅ {saved} new, {len(words) - saved} dupes")

            generated += saved
            cycle_new += saved
            existing.extend(w.get("word", "").lower().strip() for w in words)

        except Exception as e:
            _log(level, f"   ❌ Error: {e}")
            time.sleep(2)

        topic_idx += 1

        if topic_idx % len(topics) == 0:
            if cycle_new < 10:
                _log(level, f"⚠️  Only {cycle_new} new in last cycle — stopping early.")
                break
            cycle_new = 0

        time.sleep(1)

    final_count = conn.execute(
        "SELECT COUNT(*) FROM words WHERE language = ? AND level = ?",
        (language, level),
    ).fetchone()[0]
    conn.close()
    _log(level, f"✅ Done! {final_count} total ({generated} new this run)")


def export_words():
    """Export all words to JSON for bot import."""
    conn = init_db()
    rows = conn.execute(
        "SELECT word, translation, language, level, topic, sentence, sentence_with_blank, sentence_translation FROM words ORDER BY language, level, id"
    ).fetchall()
    conn.close()

    data = [
        {
            "word": r[0], "translation": r[1], "language": r[2],
            "level": r[3], "topic": r[4], "sentence": r[5],
            "sentence_with_blank": r[6], "sentence_translation": r[7],
        }
        for r in rows
    ]

    EXPORT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"✅ Exported {len(data)} words to {EXPORT_PATH}")


def show_stats():
    """Show generation statistics."""
    conn = init_db()
    rows = conn.execute(
        "SELECT language, level, COUNT(*) FROM words GROUP BY language, level ORDER BY language, level"
    ).fetchall()
    conn.close()

    if not rows:
        print("No words generated yet.")
        return

    print("\n📊 Vocabulary Stats:")
    print(f"{'Language':<12} {'Level':<8} {'Count':<8}")
    print("-" * 28)
    total = 0
    for lang, level, count in rows:
        print(f"{lang:<12} {level:<8} {count:<8}")
        total += count
    print("-" * 28)
    print(f"{'Total':<20} {total}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1].lower()

    if cmd == "export":
        export_words()
    elif cmd == "stats":
        show_stats()
    elif cmd == "seed":
        if len(sys.argv) < 3:
            print("Usage: python generate.py seed <spanish|english>")
            sys.exit(1)
        language = sys.argv[2].lower()
        targets = {"A": 800, "B": 700, "C": 500}
        print(f"🚀 Seeding {language} — A/B/C in parallel\n")
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(generate, language, lvl, cnt) for lvl, cnt in targets.items()]
            for f in futures:
                f.result()
        print()
        show_stats()
    elif cmd in ("spanish", "english"):
        if len(sys.argv) < 4:
            print("Usage: python generate.py <spanish|english> <A|B|C> <count>")
            sys.exit(1)
        level = sys.argv[2].upper()
        if level not in ("A", "B", "C"):
            print("Level must be A, B, or C")
            sys.exit(1)
        count = int(sys.argv[3])
        generate(cmd, level, count)
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)
