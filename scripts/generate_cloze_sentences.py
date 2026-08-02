#!/usr/bin/env python3
"""Generate cloze sentence cards for the Activity "cloze" game.

A cloze card is a short sentence pair (Spanish + English) where **one content
word is blanked** in the learner's *target* language; the other language is
shown as context. The player either types the missing word or picks it from
four options (three precomputed distractors + the answer).

Like the conjugation paradigms, this content is built **offline** and committed
as JSON — the deployed backend never calls an LLM on a request. This script
shells out to Amazon Bedrock (Claude Haiku 4.5) via the AWS CLI, using the
caller's ``bedrock-how`` profile (the same path the shell ``how``/``howdo``
helpers use). It batches many cards per request, validates every returned card
in Python, dedupes, buckets by difficulty, and writes:

    activity/backend/app/games/data/cloze_sentences.json

Shape::

    {
      "meta": {"model": "...", "generated_at": "...", "counts": {...}},
      "difficulties": {"beginner": "Principiante", ...},
      "cards": [
        {
          "id": "es-0001",
          "target": "es",              # language of the blanked word
          "cloze": "El ___ duerme.",   # target sentence with the blank
          "answer": "gato",            # the blanked word (canonical form)
          "context": "The cat sleeps.",# the OTHER language, full sentence
          "distractors": ["perro", "pájaro", "ratón"],
          "difficulty": "beginner"
        },
        ...
      ]
    }

Usage::

    # Refresh creds once (or rely on the script's --auth flag):
    ada credentials update --account 195950944512 --role Jaleel \\
        --provider isengard --profile bedrock-how --once

    python scripts/generate_cloze_sentences.py --total 500

The script **fails loudly** (exit 1, no write) if it can't reach Bedrock or if
too few valid cards survive validation, so a broken run can't silently ship a
tiny/empty pool. ``--dry-run`` prints what it would write without touching the
committed JSON. ``--merge`` folds new cards into the existing file (dedup-safe)
instead of replacing it, so the pool can grow over successive runs.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from _bedrock import (
    MODEL_HAIKU,
    accent_key,
    bedrock_auth,
    bedrock_converse,
    extract_json_array,
    norm,
)

# ── Paths ────────────────────────────────────────────────────────────────────
_REPO = Path(__file__).resolve().parent.parent
_OUT = _REPO / "activity" / "backend" / "app" / "games" / "data" / "cloze_sentences.json"

# ── Content shape ────────────────────────────────────────────────────────────
#: Difficulty key -> Spanish display label (shown on the freeplay setup card).
DIFFICULTIES: dict[str, str] = {
    "beginner": "Principiante",
    "intermediate": "Intermedio",
    "advanced": "Avanzado",
}

#: Target language key -> (self name, context language name) for the prompt.
_LANG_NAMES = {
    "es": ("Spanish", "English"),
    "en": ("English", "Spanish"),
}

#: How many cards to ask for per Bedrock call. Small enough to stay well under
#: the output token budget and keep a single bad batch cheap to discard.
_BATCH = 25

#: Hard floor per (target, difficulty) bucket regardless of --min-fill: a deck
#: needs at least a full daily round (10) of cards per difficulty, plus headroom
#: so the deterministic daily can pick a non-repeating set. Mirrors the engine's
#: ROUND_SIZE (kept in sync manually — both are 10).
ROUND_MIN = 10

#: Bedrock inference config — deterministic-ish, bounded output.
_MAX_TOKENS = 4096
_TEMPERATURE = 0.8


def _prompt(target: str, difficulty: str, count: int, avoid: list[str]) -> str:
    """Build the generation instruction for one (target, difficulty) batch.

    Kept extremely explicit about the JSON contract because we parse the raw
    text — any prose or markdown fence would break the batch.
    """
    target_name, context_name = _LANG_NAMES[target]
    level_hint = {
        "beginner": (
            "very common, high-frequency everyday vocabulary (top ~1000 words); "
            "short present-tense sentences of 4-7 words"
        ),
        "intermediate": (
            "mid-frequency vocabulary; sentences of 6-10 words that may use past "
            "or future tense and common connectors"
        ),
        "advanced": (
            "lower-frequency but still useful vocabulary; sentences of 8-14 words "
            "with richer structure (subjunctive, idiomatic phrasing)"
        ),
    }[difficulty]

    avoid_clause = ""
    if avoid:
        sample = ", ".join(sorted(avoid)[:60])
        avoid_clause = (
            f"\nDo NOT reuse these already-generated blank words: {sample}."
        )

    return (
        f"You are building content for a Spanish/English cloze (fill-in-the-blank) "
        f"language-learning game. Generate exactly {count} sentence pairs.\n\n"
        f"For each pair:\n"
        f"- Write a natural {target_name} sentence and its accurate {context_name} "
        f"translation.\n"
        f"- Use {level_hint}.\n"
        f"- Write the COMPLETE {target_name} sentence with every word present — do "
        f"NOT blank, mask, or replace any word yourself (no underscores).\n"
        f"- Choose ONE content word IN THE {target_name.upper()} SENTENCE as the "
        f"answer. It MUST be a meaningful noun, verb, adjective, or adverb — "
        f"NEVER an article, preposition, pronoun, conjunction, or number.\n"
        f"- The answer word must appear EXACTLY as written in the {target_name} "
        f"sentence (same spelling and accents, case-insensitive).\n"
        f"- Provide exactly 3 distractor words in {target_name}: the same part of "
        f"speech AND the same grammatical form (tense, mood, number, gender) as "
        f"the answer, but each clearly WRONG in this sentence because its MEANING "
        f"does not fit. A distractor must NEVER be a synonym or near-synonym of "
        f"the answer, and must never be an equally-correct alternative — exactly "
        f"one word (the answer) may correctly complete the sentence. All three "
        f"distractors differ from each other and from the answer.\n"
        f"- Grammar must be correct: if the sentence needs the subjunctive "
        f"(e.g. after 'dudo que', 'es posible que', 'prefiero que', 'para que', "
        f"'ojalá'), the answer AND all distractors must be in the correct "
        f"subjunctive form. The answer's tense/mood must match the "
        f"{context_name} translation (a past-tense translation needs a past-tense "
        f"answer, etc.).\n"
        f"- Keep sentences wholesome and generally useful for learners.{avoid_clause}\n\n"
        f'Return ONLY a JSON array of exactly {count} objects, no prose, no markdown '
        f'fences. Each object: '
        f'{{"target":"{target_name} sentence","context":"{context_name} translation",'
        f'"answer":"the blanked word","distractors":["w1","w2","w3"]}}'
    )


# Word-boundary match that is Unicode-aware (Python's \b treats accented letters
# as word chars), so we can confirm the answer appears as a whole word and build
# the blanked form by replacing that occurrence.
def _blank_sentence(sentence: str, answer: str) -> str | None:
    """Return the sentence with the answer occurrence replaced by ``___``.

    Two paths:
    * The model already inserted a blank (a run of underscores) — normalize
      that run to a single ``___`` token and accept it. We can't re-verify the
      answer position in this case, so we trust the separately-provided answer.
    * The full sentence is present — replace the first whole-word, case
      -insensitive, accent-sensitive occurrence of ``answer`` with ``___``.

    Returns ``None`` if neither a blank nor the answer word is found (the card
    is then rejected rather than shipped with a broken prompt).
    """
    # Path 1: model pre-blanked the sentence (one or more underscores).
    if "_" in sentence:
        collapsed = re.sub(r"_+", "___", sentence)
        # Guard against a runaway (multiple separate blanks) — keep only if
        # there is exactly one blank token.
        if collapsed.count("___") == 1:
            return collapsed
        return None

    # Path 2: full sentence — blank the answer's first whole-word occurrence.
    pattern = re.compile(rf"(?<!\w){re.escape(answer)}(?!\w)", re.IGNORECASE)
    if not pattern.search(sentence):
        return None
    return pattern.sub("___", sentence, count=1)


def _validate_card(
    raw: Any, target: str, difficulty: str, seen_answers: set[str],
) -> dict[str, Any] | None:
    """Turn one raw model object into a validated card, or ``None`` to reject.

    Rejection reasons: wrong shape, missing fields, answer not a whole word in
    the sentence, fewer than 3 distinct distractors, or the answer collides
    with a distractor. ``seen_answers`` is advisory (variety), not a hard gate.
    """
    if not isinstance(raw, dict):
        return None
    sentence = raw.get("target")
    context = raw.get("context")
    answer = raw.get("answer")
    distractors = raw.get("distractors")
    if not (isinstance(sentence, str) and sentence.strip()):
        return None
    if not (isinstance(context, str) and context.strip()):
        return None
    if not (isinstance(answer, str) and answer.strip()):
        return None
    if not isinstance(distractors, list):
        return None

    sentence = sentence.strip()
    context = context.strip()
    answer = answer.strip()

    cloze = _blank_sentence(sentence, answer)
    if cloze is None:
        return None  # answer not present as a whole word — unusable prompt

    # Distractors: strings, non-empty, distinct from each other and the answer.
    # Dedup on the ACCENT-STRIPPED key (not just _norm), because the runtime
    # grader awards full credit (CLOSE) when a guess matches ignoring accents —
    # so a distractor that differs from the answer only by accents would grade
    # as correct if picked. Rejecting on _accent_key keeps validation aligned
    # with grading and prevents that false-positive.
    clean_distractors: list[str] = []
    seen_local = {accent_key(answer)}
    for d in distractors:
        if not isinstance(d, str):
            continue
        d = d.strip()
        key = accent_key(d)
        if not d or key in seen_local:
            continue
        seen_local.add(key)
        clean_distractors.append(d)
    if len(clean_distractors) < 3:
        return None
    clean_distractors = clean_distractors[:3]

    return {
        "target": target,
        "cloze": cloze,
        "answer": answer,
        "context": context,
        "distractors": clean_distractors,
        "difficulty": difficulty,
    }


def _card_id(target: str, index: int) -> str:
    return f"{target}-{index:04d}"


def _dedup_key(card: dict[str, Any]) -> tuple[str, str, str]:
    """Cards are the same if same target + same answer + same blanked sentence."""
    return (card["target"], norm(card["answer"]), norm(card["cloze"]))


def _generate(
    target: str, difficulty: str, want: int, verbose: bool,
) -> list[dict[str, Any]]:
    """Generate ~``want`` validated cards for one (target, difficulty)."""
    cards: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    answers: set[str] = set()
    attempts = 0
    max_attempts = (want // _BATCH + 1) * 3  # bounded retries for a bad batch
    while len(cards) < want and attempts < max_attempts:
        attempts += 1
        batch_n = min(_BATCH, want - len(cards) + 5)  # slight over-ask
        prompt = _prompt(target, difficulty, batch_n, list(answers))
        try:
            text = bedrock_converse(prompt, model=MODEL_HAIKU, max_tokens=_MAX_TOKENS, temperature=_TEMPERATURE)
        except RuntimeError as exc:
            print(f"  ! {target}/{difficulty}: {exc}", file=sys.stderr)
            time.sleep(2)
            continue
        raw_items = extract_json_array(text)
        if not raw_items:
            print(f"  ! {target}/{difficulty}: no JSON parsed from batch", file=sys.stderr)
            continue
        added = 0
        for raw in raw_items:
            card = _validate_card(raw, target, difficulty, answers)
            if card is None:
                continue
            key = _dedup_key(card)
            if key in seen:
                continue
            seen.add(key)
            answers.add(norm(card["answer"]))
            cards.append(card)
            added += 1
            if len(cards) >= want:
                break
        if verbose:
            print(
                f"  · {target}/{difficulty}: +{added} "
                f"({len(cards)}/{want}) [attempt {attempts}]"
            )
        time.sleep(0.5)  # gentle pacing
    return cards


def _assign_ids(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Assign stable per-target ids in list order (es-0001, en-0001, …)."""
    counters: dict[str, int] = {}
    out: list[dict[str, Any]] = []
    for card in cards:
        t = card["target"]
        counters[t] = counters.get(t, 0) + 1
        out.append({"id": _card_id(t, counters[t]), **card})
    return out


def _load_existing() -> list[dict[str, Any]]:
    if not _OUT.exists():
        return []
    try:
        data = json.loads(_OUT.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    cards = data.get("cards", [])
    return cards if isinstance(cards, list) else []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--total", type=int, default=500,
        help="total cards to generate across both directions (default: 500)",
    )
    parser.add_argument(
        "--targets", default="es,en",
        help="comma-separated target languages to build (default: es,en)",
    )
    parser.add_argument(
        "--merge", action="store_true",
        help="merge new cards into the existing JSON instead of replacing it",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="print a summary without writing the JSON",
    )
    parser.add_argument(
        "--min-fill", type=float, default=0.8,
        help=("minimum fraction of each bucket's per-difficulty target that must "
              "be reached before writing (default: 0.8); ignored with --merge"),
    )
    parser.add_argument(
        "--allow-underfill", action="store_true",
        help="write even if some buckets fall below --min-fill (after review)",
    )
    parser.add_argument(
        "--no-auth", action="store_true",
        help="skip the `ada credentials update` refresh (assume creds are fresh)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    targets = [t.strip() for t in args.targets.split(",") if t.strip()]
    for t in targets:
        if t not in _LANG_NAMES:
            print(f"unknown target language: {t!r} (want one of {list(_LANG_NAMES)})",
                  file=sys.stderr)
            return 1

    if not args.no_auth:
        print("Refreshing Bedrock credentials (bedrock-how)…")
        bedrock_auth()

    # Split the total evenly across targets, then evenly across difficulties.
    per_target = args.total // len(targets)
    per_difficulty = max(1, per_target // len(DIFFICULTIES))

    print(
        f"Generating ~{args.total} cards: {len(targets)} target(s) × "
        f"{len(DIFFICULTIES)} difficulties (~{per_difficulty} each) via {MODEL_HAIKU}"
    )

    fresh: list[dict[str, Any]] = []
    for target in targets:
        for difficulty in DIFFICULTIES:
            print(f"→ {target} / {difficulty} (want {per_difficulty})…")
            fresh.extend(_generate(target, difficulty, per_difficulty, args.verbose))

    if not fresh:
        print("No cards generated — refusing to write.", file=sys.stderr)
        return 1

    # Merge with existing if asked, deduping across old + new.
    combined: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    source = (_load_existing() if args.merge else []) + fresh
    for card in source:
        # Strip any pre-existing id; we reassign contiguously below.
        card = {k: v for k, v in card.items() if k != "id"}
        key = _dedup_key(card)
        if key in seen:
            continue
        seen.add(key)
        combined.append(card)

    # Sort beginner→advanced, then by target, so the pools read in a sensible
    # order in the committed file (the engine re-picks; order is cosmetic).
    difficulty_rank = {k: i for i, k in enumerate(DIFFICULTIES)}
    combined.sort(key=lambda c: (difficulty_rank.get(c["difficulty"], 99), c["target"]))
    combined = _assign_ids(combined)

    # Count for the report + meta.
    counts: dict[str, int] = {}
    for card in combined:
        bucket = f"{card['target']}/{card['difficulty']}"
        counts[bucket] = counts.get(bucket, 0) + 1

    print("\nFinal counts:")
    for bucket in sorted(counts):
        print(f"  {bucket}: {counts[bucket]}")
    print(f"  TOTAL: {len(combined)}")

    # Underfill guard: a partially-successful run (Bedrock throttling, a run of
    # unparseable batches) can leave a bucket far short of target. Writing that
    # would silently replace a healthy corpus with a lopsided one — e.g. a deck
    # with too few cards for a non-repeating daily round. Refuse unless every
    # (target, difficulty) bucket reaches --min-fill of its per-difficulty goal.
    # --merge is exempt (the existing pool backstops thin new buckets); a run
    # can still be forced with --allow-underfill after review.
    if not args.merge:
        floor = max(ROUND_MIN, int(per_difficulty * args.min_fill))
        thin = {
            f"{t}/{dfc}": counts.get(f"{t}/{dfc}", 0)
            for t in targets for dfc in DIFFICULTIES
            if counts.get(f"{t}/{dfc}", 0) < floor
        }
        if thin:
            print(
                f"\nUnderfilled buckets (< {floor} = {args.min_fill:.0%} of "
                f"{per_difficulty}):",
                file=sys.stderr,
            )
            for bucket in sorted(thin):
                print(f"  - {bucket}: {thin[bucket]}", file=sys.stderr)
            if not args.allow_underfill:
                print(
                    "\nRefusing to write a lopsided corpus (would shrink a deck's "
                    "daily/freeplay pool). Re-run — or pass --allow-underfill once "
                    "you've accepted these counts, or --merge to top up in place.",
                    file=sys.stderr,
                )
                return 1
            print("\n--allow-underfill set: writing the thin corpus anyway.",
                  file=sys.stderr)

    if args.dry_run:
        print("\n--dry-run: not writing. Sample cards:")
        for card in combined[:3]:
            print(json.dumps(card, ensure_ascii=False, indent=2))
        return 0

    out = {
        "meta": {
            "model": MODEL_HAIKU,
            "generated_at": datetime.now(UTC).isoformat(),
            "counts": counts,
            "total": len(combined),
        },
        "difficulties": DIFFICULTIES,
        "cards": combined,
    }
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"\nWrote {len(combined)} cards -> {_OUT.relative_to(_REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
