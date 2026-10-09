#!/usr/bin/env python3
"""Generate wordle_lexicon.json from the 334-word answer list via Bedrock.

Two-pass process:
1. **Generate** (Haiku): batches of ~40 words → lexicon entries with display,
   pos, en, example_es, example_en, lemma, form fields.
2. **Review** (Opus): batch-review each generated entry; apply corrections or
   flag irreparably bad entries so they can be manually fixed.

Usage::

    cd /path/to/repo
    uv run --with pyyaml scripts/generate_wordle_lexicon.py

Output: activity/backend/app/games/data/wordle_lexicon.json
Progress checkpoint: /tmp/wordle_lexicon_progress.json (resume if interrupted)
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# Make scripts/ importable regardless of CWD.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _bedrock import (
    MODEL_HAIKU,
    MODEL_OPUS,
    bedrock_auth,
    bedrock_converse,
    extract_json_array,
)

ANSWERS_FILE = Path(__file__).resolve().parent.parent / "activity" / "backend" / "app" / "games" / "data" / "wordle_answers.txt"
OUT_FILE = Path(__file__).resolve().parent.parent / "activity" / "backend" / "app" / "games" / "data" / "wordle_lexicon.json"
CHECKPOINT = Path("/tmp/wordle_lexicon_progress.json")

BATCH_SIZE = 40
VALID_POS = {"noun", "verb", "adjective", "adverb", "other"}

REQUIRED_KEYS = {"display", "pos", "en", "example_es", "example_en", "lemma", "form"}
ALLOWED_KEYS = REQUIRED_KEYS  # no extra keys permitted


def load_answers() -> list[str]:
    return [ln.strip() for ln in ANSWERS_FILE.read_text(encoding="utf-8").splitlines() if ln.strip()]


def load_checkpoint() -> dict[str, dict]:
    if CHECKPOINT.exists():
        try:
            return json.loads(CHECKPOINT.read_text())
        except json.JSONDecodeError:
            pass
    return {}


def save_checkpoint(data: dict[str, dict]) -> None:
    CHECKPOINT.write_text(json.dumps(data, ensure_ascii=False, indent=2))


_GENERATE_SYSTEM = """\
You are a Spanish language expert generating structured vocabulary cards for a
Spanish Wordle learning app. Learners are A1–B1 English-speaking adults.

For each normalized Spanish word I give you, produce a JSON object with EXACTLY
these keys:
  display   — canonical spelling with correct accents (e.g. "árbol" not "arbol")
  pos       — one of: noun | verb | adjective | adverb | other
  en        — short English gloss (≤6 words, no article, no period)
  example_es — one short Spanish sentence (≤12 words) that contains the EXACT
               display word (not a different inflection). Must be A1–B1 level.
  example_en — accurate English translation of example_es
  lemma     — dictionary lemma (e.g. "hablar" for any conjugated form)
  form      — empty string "" for dictionary-form answers; a short English
              description for inflected forms (e.g. "3rd sg. preterite of comer",
              "plural of agua"). Never put grammar info in this field for
              dictionary-form words.

CRITICAL RULES:
- The EXACT display word (same characters, same accent marks) must appear
  verbatim in example_es. Not a synonym, not a different form.
- example_es and example_en must be accurate translations of each other.
- No extra keys. No notes. No explanations outside the JSON.
- respond with ONLY a valid JSON array of objects (no markdown, no prose).
"""


def generate_batch(words: list[str]) -> list[dict]:
    word_list = "\n".join(f"- {w}" for w in words)
    prompt = f"""{_GENERATE_SYSTEM}

Generate vocabulary cards for these {len(words)} Spanish words:
{word_list}

Respond with a JSON array of {len(words)} objects, one per word in the same order."""

    for attempt in range(3):
        try:
            raw = bedrock_converse(prompt, model=MODEL_HAIKU, max_tokens=6000, temperature=0.3)
            entries = extract_json_array(raw)
            if len(entries) == len(words):
                return entries
            print(f"  [gen] got {len(entries)} entries for {len(words)} words, retrying…", flush=True)
        except RuntimeError as exc:
            print(f"  [gen] attempt {attempt+1} failed: {exc}", flush=True)
            if attempt < 2:
                time.sleep(5)
    # Partial results: build what we can, fill gaps with None
    return entries if entries else []


_REVIEW_SYSTEM = """\
You are a senior Spanish language editor reviewing vocabulary cards for a
Spanish Wordle learning app (A1–B1 adult learners).

Each card has: display, pos, en, example_es, example_en, lemma, form.

For each card:
1. Check that the EXACT display word appears verbatim in example_es.
2. Check that example_en is an accurate translation.
3. Check that pos, en, lemma, form are correct.
4. If anything is wrong, output a corrected version with the SAME keys.
5. If everything is correct, return the card unchanged.

NEVER change the "display" field — it is authoritative.
NEVER add extra keys.
Respond with ONLY a valid JSON array of corrected objects.
"""


def review_batch(entries: list[dict]) -> list[dict]:
    cards_json = json.dumps(entries, ensure_ascii=False, indent=2)
    prompt = f"""{_REVIEW_SYSTEM}

Review and correct these {len(entries)} vocabulary cards:
{cards_json}

Return a JSON array of {len(entries)} corrected objects."""

    for attempt in range(3):
        try:
            raw = bedrock_converse(prompt, model=MODEL_OPUS, max_tokens=8000, temperature=None)
            reviewed = extract_json_array(raw)
            if len(reviewed) == len(entries):
                return reviewed
            print(f"  [rev] got {len(reviewed)} entries for {len(entries)}, using original", flush=True)
            return entries
        except RuntimeError as exc:
            print(f"  [rev] attempt {attempt+1} failed: {exc}", flush=True)
            if attempt < 2:
                time.sleep(8)
    return entries


def validate_entry(word: str, entry: dict) -> list[str]:
    """Return list of validation errors for an entry (empty = ok)."""
    errors = []
    extra = set(entry.keys()) - ALLOWED_KEYS
    if extra:
        errors.append(f"extra keys: {extra}")
    missing = ALLOWED_KEYS - set(entry.keys())
    if missing:
        errors.append(f"missing keys: {missing}")
    pos = entry.get("pos", "")
    if pos not in VALID_POS:
        errors.append(f"invalid pos '{pos}'")
    for field in ("en", "example_es", "example_en"):
        if not entry.get(field, "").strip():
            errors.append(f"empty {field}")
    display: str = entry.get("display", "")
    if not display:
        errors.append("empty display")
    else:
        # example_es must contain display verbatim (case-insensitive)
        if display.lower() not in entry.get("example_es", "").lower():
            errors.append(f"example_es missing display '{display}'")
    return errors


def main() -> None:
    bedrock_auth()
    print("Credentials refreshed.", flush=True)

    answers = load_answers()
    print(f"Loaded {len(answers)} answers.", flush=True)

    progress: dict[str, dict] = load_checkpoint()
    remaining = [w for w in answers if w not in progress]
    print(f"Already done: {len(progress)}, remaining: {len(remaining)}", flush=True)

    # ── generation pass ────────────────────────────────────────────────────
    for batch_start in range(0, len(remaining), BATCH_SIZE):
        batch = remaining[batch_start : batch_start + BATCH_SIZE]
        print(f"\nGenerating batch {batch_start // BATCH_SIZE + 1}: {batch}", flush=True)
        entries = generate_batch(batch)
        # Map entries back to words by position
        for i, word in enumerate(batch):
            entry = entries[i] if i < len(entries) else {}
            if not isinstance(entry, dict):
                entry = {}
            progress[word] = entry
        save_checkpoint(progress)
        time.sleep(1)  # rate-limit courtesy pause

    # ── review pass (Opus) ─────────────────────────────────────────────────
    print("\nStarting Opus review pass…", flush=True)
    all_words = list(answers)
    reviewed: dict[str, dict] = {}

    for batch_start in range(0, len(all_words), BATCH_SIZE):
        batch = all_words[batch_start : batch_start + BATCH_SIZE]
        batch_entries = [progress.get(w, {}) for w in batch]
        print(f"  Reviewing batch {batch_start // BATCH_SIZE + 1} ({len(batch)} entries)…", flush=True)
        corrected = review_batch(batch_entries)
        for i, word in enumerate(batch):
            reviewed[word] = corrected[i] if i < len(corrected) else progress.get(word, {})
        time.sleep(1)

    # ── validate + report ──────────────────────────────────────────────────
    print("\nValidation report:", flush=True)
    bad_words = []
    final: dict[str, dict] = {}
    for word in answers:
        entry = reviewed.get(word, {})
        errs = validate_entry(word, entry)
        if errs:
            print(f"  FAIL {word}: {errs}", flush=True)
            bad_words.append(word)
        else:
            final[word] = entry

    print(f"\n{len(final)}/{len(answers)} entries passed validation.", flush=True)
    if bad_words:
        print(f"FAILED ({len(bad_words)}): {bad_words}", flush=True)

    # Write the output: always include all words; failed entries preserved as-is
    # so they can be manually corrected.
    for word in answers:
        if word not in final:
            final[word] = reviewed.get(word, progress.get(word, {}))

    OUT_FILE.write_text(json.dumps(final, ensure_ascii=False, indent=2) + "\n")
    print(f"\nWrote {OUT_FILE}", flush=True)

    if bad_words:
        print(f"\n⚠️  {len(bad_words)} entries need manual review: {bad_words}", flush=True)
        sys.exit(1)
    else:
        print("\n✅  All 334 entries validated.", flush=True)


if __name__ == "__main__":
    main()
