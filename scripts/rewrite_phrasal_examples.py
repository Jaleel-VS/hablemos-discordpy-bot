#!/usr/bin/env python3
"""Rewrite the phrasal-verb corpus into plain, everyday learner English.

The examples in ``phrasal_verbs.json`` came from a scraped dataset: news and
fiction fragments with no context ("Both sides ___ last night 's clash on the
back of awful runs."), senses that don't match the definition shown, and
obscure or regional verbs. This script replaces the teaching material on every
card while keeping the verb list, ids and accepted forms:

1. **Generate** (Opus): for each verb, choose the most common everyday sense
   and write one learner-friendly definition, a Spanish gloss for *that*
   sense, a natural 6–14 word sentence using it, a CEFR band, three particle
   distractors that do *not* fit the sentence, or ``keep: false`` for verbs a
   learner doesn't need (rare, archaic, vulgar, very regional).
2. **Validate** deterministically: exactly one blank, the filled span is an
   accepted form, verb and particle are contiguous (so particle mode can blank
   just the particle), distractors are distinct single particles, sentence
   length.
3. **Review** (Opus, separate critic prompt with fresh context): would a
   native speaker say this? Does the gloss match the sense used? Could a
   distractor also be correct? It returns ``ok``, ``fix`` (with corrected
   fields, re-validated) or ``drop``.

Ids of kept verbs are unchanged, so in-flight sealed games and review rounds
still resolve. Dropped verbs go to ``phrasal_verbs.dropped.json`` for audit
(never loaded at runtime). Fails closed: a verb that never produces a valid,
approved card is dropped, not shipped with its old example.

Usage::

    python scripts/rewrite_phrasal_examples.py --auth            # full run
    python scripts/rewrite_phrasal_examples.py --limit 40 --dry-run

Progress is checkpointed to ``/tmp/phrasal_rewrite_progress.json`` so an
interrupted run (expired credentials) resumes where it stopped.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bedrock import (
    MODEL_OPUS,
    bedrock_auth,
    bedrock_converse,
    extract_json_array,
)

_REPO = Path(__file__).resolve().parent.parent
_DATA = _REPO / "activity" / "backend" / "app" / "games" / "data" / "phrasal_verbs.json"
_DROPPED = _DATA.with_name("phrasal_verbs.dropped.json")
_CHECKPOINT = Path("/tmp/phrasal_rewrite_progress.json")

_BATCH = 20
_AUDIT_BATCH = 40
_WORKERS = 6
_MAX_TOKENS = 8000
#: Editor decisions after reading the output: verbs that only sound natural
#: with the object between verb and particle ("make it up to you", "drummed
#: it into me"), which the contiguous-span format can't express, so every
#: rewrite came out stilted. Dropped by name so a rerun reproduces the corpus.
_EDITOR_DROP = {
    "do in": "only natural split (did me in)",
    "make up to": "needs 'it' (make it up to)",
    "put into": "only natural split (put effort into)",
    "drum into": "only natural split (drummed it into me)",
    "read into": "only natural split (read too much into)",
    "keep in": "only natural split (kept them in)",
    "hold over": "rare; learners use 'put off'",
}
_DIFFICULTIES = {"beginner", "intermediate", "advanced"}
_BLANK = "___"
#: Single-word particles allowed as multiple-choice distractors.
_PARTICLES = {
    "up", "down", "in", "out", "on", "off", "over", "back", "away", "around",
    "about", "along", "through", "across", "by", "for", "into", "onto", "with",
    "after", "ahead", "apart", "aside", "forward", "together", "under", "at",
    "to", "from", "of",
}
_MIN_WORDS = 5
_MAX_WORDS = 16

_GENERATE = """\
You write flashcards that teach English phrasal verbs to Spanish speakers \
(roughly A2–B2). For EACH verb below, produce one card.

Rules:
- Pick the verb's MOST COMMON everyday sense, the one a learner will actually \
hear. Ignore rare or literary senses.
- definition: one short, plain-English definition of that sense (max 12 \
words, simple vocabulary, no "etc").
- gloss_es: a short natural Spanish equivalent of THAT sense (1–5 words; two \
options may be separated by a comma).
- sentence: ONE natural sentence a native speaker would really say in daily \
life (home, work, school, friends, shopping, travel, health, weather). 6–14 \
words. Simple vocabulary apart from the verb. Self-contained: no names of \
real people, no news-speak, no idioms besides the verb, no unexplained \
pronouns like "it" with no referent. Contractions are fine.
- In the sentence, the phrasal verb must appear exactly once, with the verb \
and particle TOGETHER (e.g. "picked up the kids", never "picked the kids \
up"). Wrap that span in [square brackets], e.g. "Can you [pick up] some milk \
on the way home?". The bracketed span must be one of the listed forms \
(capitalise only if it starts the sentence).
- distractors: three single-word particles from {particles} that are NOT the \
answer and that would be WRONG in this sentence with this base verb (no \
other valid phrasal verb, even with a different meaning).
- difficulty: "beginner" (very common, A1–A2: get up, turn off), \
"intermediate" (B1: figure out, put off), "advanced" (B2+, less frequent).
- keep: false if a learner does not need this verb (rare, archaic, vulgar, \
mostly regional slang, or only used in a narrow technical field). Then the \
other fields may be empty. Be honest; keeping a weird verb hurts learners.

Verbs:
{verbs}

Return ONLY a JSON array, one object per verb, no prose:
{{"id": "...", "keep": true, "definition": "...", "gloss_es": "...", \
"sentence": "...", "distractors": ["...", "...", "..."], \
"difficulty": "beginner|intermediate|advanced"}}
"""

_REVIEW = """\
You are a strict native-speaker editor checking English phrasal-verb \
flashcards for Spanish-speaking learners (A2–B2). The verb is shown in \
[brackets] in each sentence. In the game, the learner sees the sentence with \
the particle blanked out and picks it from four options (the answer plus the \
distractors).

For EACH card, check:
1. natural — would a native speaker actually say this sentence in everyday \
life? Reject anything stilted, odd, newsy, literary, ambiguous or confusing \
for a learner.
2. sense — the definition and the Spanish gloss both match the sense used in \
the sentence, and the gloss is correct, natural Spanish.
3. distractors — none of them could also be correct in the sentence with the \
same base verb. Replacements must be single words from: {particles}.
4. level — difficulty is about right.
5. worth it — a learner should learn this verb at all.

Verdict:
- "ok": everything is good.
- "fix": return corrected fields (only the ones you change). A fixed \
sentence must keep exactly ONE [bracketed] span, 6–14 words, and the span \
must be the verb and particle TOGETHER, using one of the listed forms. Never \
split them with a pronoun ("let you down"): if the natural sentence needs \
one, use a noun object after the particle or the passive instead \
("I felt [let down] by the ending", "Please [pay back] the money").
- "drop": the verb itself isn't worth teaching (rare, archaic, vulgar, very \
regional).

Cards:
{cards}

Return ONLY a JSON array, no prose:
{{"id": "...", "verdict": "ok|fix|drop", "reason": "short", \
"definition": "...", "gloss_es": "...", "sentence": "...", \
"distractors": ["...", "...", "..."], "difficulty": "..."}}
(omit unchanged fields on "fix"; omit all fields on "ok"/"drop").
"""


def _verb_lines(verbs: list[dict[str, Any]]) -> str:
    return "\n".join(
        f'- id: {v["id"]} | verb: "{v["verb"]}" | particle: "{v["particle"]}" '
        f'| forms: {json.dumps(v["forms"])}'
        for v in verbs
    )


def _card_lines(verbs: dict[str, dict[str, Any]], cards: dict[str, dict[str, Any]]) -> str:
    lines = []
    for vid, card in cards.items():
        v = verbs[vid]
        lines.append(
            f'- id: {vid} | verb: "{v["verb"]}" | forms: {json.dumps(v["forms"])} '
            f'| definition: "{card["definition"]}" '
            f'| gloss_es: "{card["gloss_es"]}" | sentence: "{card["sentence"]}" '
            f'| distractors: {json.dumps(card["distractors"])} | difficulty: {card["difficulty"]}'
        )
    return "\n".join(lines)


def _call(prompt: str) -> list[Any]:
    """One Opus call → parsed JSON array; one retry on an unparseable reply.

    Bedrock CLI failures propagate as ``RuntimeError`` so the run aborts
    (and resumes from the checkpoint) instead of dropping verbs.
    """
    for _ in range(2):
        items = extract_json_array(
            bedrock_converse(prompt, model=MODEL_OPUS, max_tokens=_MAX_TOKENS, temperature=None)
        )
        if items:
            return items
    return []


def _str(value: Any) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def _card_from(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize one model object into a card dict with concrete types."""
    distractors = item.get("distractors")
    return {
        "definition": _str(item.get("definition")),
        "gloss_es": _str(item.get("gloss_es")),
        "sentence": _str(item.get("sentence")),
        "distractors": [
            _str(d).lower() for d in distractors if isinstance(d, str)
        ] if isinstance(distractors, list) else [],
        "difficulty": _str(item.get("difficulty")).lower(),
    }


_BRACKET = re.compile(r"\[([^\[\]]+)\]")


def validate(verb: dict[str, Any], card: dict[str, Any]) -> list[str]:
    """Deterministic checks; returns problems (empty means the card is usable)."""
    problems: list[str] = []
    spans = _BRACKET.findall(card["sentence"])
    if len(spans) != 1:
        return [f"need exactly one [bracketed] span, got {len(spans)}"]
    span = spans[0].strip()
    if span.lower() not in verb["forms"]:
        problems.append(f"span {span!r} not an accepted form")
    if not span.lower().endswith(" " + verb["particle"]):
        problems.append("verb and particle not contiguous")
    words = len(card["sentence"].split())
    if not _MIN_WORDS <= words <= _MAX_WORDS:
        problems.append(f"sentence has {words} words")
    if _BLANK in card["sentence"]:
        problems.append("sentence contains a literal blank")
    d = card["distractors"]
    if len(d) != 3 or len(set(d)) != 3 or verb["particle"] in d or not set(d) <= _PARTICLES:
        problems.append(f"bad distractors {d}")
    if card["difficulty"] not in _DIFFICULTIES:
        problems.append(f"bad difficulty {card['difficulty']!r}")
    if not card["definition"] or len(card["definition"].split()) > 16:
        problems.append("bad definition")
    if not card["gloss_es"] or len(card["gloss_es"].split()) > 8:
        problems.append("bad gloss")
    return problems


def _apply(verb: dict[str, Any], card: dict[str, Any]) -> dict[str, Any]:
    """Merge a validated card into the verb entry (id, forms, verb unchanged)."""
    span = _BRACKET.search(card["sentence"])
    if span is None:  # validate() already guarantees one span
        raise ValueError(verb["id"])
    out = dict(verb)
    out["definitions"] = [card["definition"]]
    out["gloss_es"] = card["gloss_es"]
    out["example"] = card["sentence"][: span.start()] + _BLANK + card["sentence"][span.end():]
    out["example_answer"] = span.group(1).strip()
    out["distractors_particle"] = card["distractors"]
    out["difficulty"] = card["difficulty"]
    return out


def process_batch(verbs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Generate → validate → review → re-validate one batch.

    Returns ``{id: {"status": "kept", "entry": …}}`` or
    ``{id: {"status": "dropped", "reason": …}}`` for every verb in the batch.
    """
    by_id = {v["id"]: v for v in verbs}
    results: dict[str, dict[str, Any]] = {}
    pending = list(verbs)
    cards: dict[str, dict[str, Any]] = {}

    # Generate, with one regeneration round for cards that fail validation.
    for attempt in range(2):
        if not pending:
            break
        items = _call(_GENERATE.format(particles=", ".join(sorted(_PARTICLES)), verbs=_verb_lines(pending)))
        retry: list[dict[str, Any]] = []
        got = {i.get("id"): i for i in items if isinstance(i, dict)}
        for v in pending:
            item = got.get(v["id"])
            if item is None:
                retry.append(v)
                continue
            if item.get("keep") is False:
                results[v["id"]] = {"status": "dropped", "reason": "generator: not worth teaching"}
                continue
            card = _card_from(item)
            problems = validate(v, card)
            if problems and attempt == 0:
                retry.append(v)
            elif problems:
                results[v["id"]] = {"status": "dropped", "reason": "invalid: " + "; ".join(problems)}
            else:
                cards[v["id"]] = card
        pending = retry
    for v in pending:
        results.setdefault(v["id"], {"status": "dropped", "reason": "generator returned nothing"})

    if not cards:
        return results

    verdicts = {
        i.get("id"): i
        for i in _call(_REVIEW.format(
            particles=", ".join(sorted(_PARTICLES)), cards=_card_lines(by_id, cards),
        ))
        if isinstance(i, dict)
    }
    for vid, card in cards.items():
        verdict = verdicts.get(vid)
        if verdict is None:
            results[vid] = {"status": "dropped", "reason": "unreviewed"}
            continue
        kind = verdict.get("verdict")
        if kind == "drop":
            results[vid] = {"status": "dropped", "reason": "review: " + _str(verdict.get("reason"))}
            continue
        if kind == "fix":
            patch = _card_from(verdict)
            card = {k: (patch[k] or card[k]) for k in card}
        elif kind != "ok":
            results[vid] = {"status": "dropped", "reason": f"bad verdict {kind!r}"}
            continue
        problems = validate(by_id[vid], card)
        if problems:
            results[vid] = {"status": "dropped", "reason": "invalid after review: " + "; ".join(problems)}
            continue
        results[vid] = {
            "status": "kept",
            "entry": _apply(by_id[vid], card),
            "fixed": kind == "fix",
        }
    return results


_AUDIT = """\
You are proofreading the finished English sentences of a phrasal-verb game \
for Spanish speakers (A2–B2). The phrasal verb is in [brackets].

Flag ONLY sentences a native speaker would find unnatural, odd, forced, \
ambiguous, or where the verb is used in a strange sense. Most are fine; do \
not flag a sentence just because you'd phrase it differently.

For each flagged card return a corrected sentence: 6–14 words, everyday \
situation, exactly ONE [bracketed] span using one of the listed forms, verb \
and particle together. Also return gloss_es and definition if the sense \
changes. If the verb can't be used naturally with verb and particle together, \
return "drop": true.

Cards:
{cards}

Return ONLY a JSON array of the flagged cards (empty array if none):
{{"id": "...", "reason": "short", "sentence": "...", "gloss_es": "...", \
"definition": "...", "drop": false}}
"""


def _as_card(entry: dict[str, Any]) -> dict[str, Any]:
    """Rebuild a bracketed card from a stored entry (for the audit pass)."""
    return {
        "definition": entry["definitions"][0],
        "gloss_es": entry["gloss_es"],
        "sentence": entry["example"].replace(_BLANK, f"[{entry['example_answer']}]", 1),
        "distractors": entry["distractors_particle"],
        "difficulty": entry["difficulty"],
    }


def audit_batch(entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Second-opinion naturalness pass over finished cards.

    Returns results only for the cards it changes: a re-validated rewrite
    (``kept``) or ``dropped``. Unflagged cards are absent and stay as they are.
    """
    by_id = {e["id"]: e for e in entries}
    cards = {e["id"]: _as_card(e) for e in entries}
    lines = "\n".join(
        f'- id: {vid} | forms: {json.dumps(by_id[vid]["forms"])} | sentence: "{c["sentence"]}"'
        for vid, c in cards.items()
    )
    out: dict[str, dict[str, Any]] = {}
    for item in _call(_AUDIT.format(cards=lines)) if entries else []:
        if not isinstance(item, dict) or item.get("id") not in by_id:
            continue
        vid = item["id"]
        reason = _str(item.get("reason"))
        if item.get("drop") is True:
            out[vid] = {"status": "dropped", "reason": "audit: " + reason}
            continue
        patch = _card_from(item)
        card = {k: (patch[k] or cards[vid][k]) for k in cards[vid]}
        card["distractors"] = cards[vid]["distractors"]
        card["difficulty"] = cards[vid]["difficulty"]
        problems = validate(by_id[vid], card)
        if problems:
            out[vid] = {"status": "dropped", "reason": "audit rewrite invalid: " + "; ".join(problems)}
        else:
            out[vid] = {"status": "kept", "entry": _apply(by_id[vid], card), "fixed": True, "audited": reason}
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Rewrite phrasal examples into everyday English.")
    parser.add_argument("--auth", action="store_true", help="Refresh Bedrock creds first.")
    parser.add_argument("--limit", type=int, default=0, help="Only the first N verbs (debug).")
    parser.add_argument("--dry-run", action="store_true", help="Report only; don't write the corpus.")
    args = parser.parse_args()

    if args.auth:
        bedrock_auth()

    payload = json.loads(_DATA.read_text(encoding="utf-8"))
    verbs: list[dict[str, Any]] = payload["verbs"]
    if args.limit > 0:
        verbs = verbs[: args.limit]

    done: dict[str, dict[str, Any]] = (
        json.loads(_CHECKPOINT.read_text(encoding="utf-8")) if _CHECKPOINT.exists() else {}
    )
    todo = [v for v in verbs if v["id"] not in done]
    batches = [todo[i : i + _BATCH] for i in range(0, len(todo), _BATCH)]
    print(f"{len(done)} done from checkpoint, {len(todo)} to process in {len(batches)} batches", flush=True)

    try:
        with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
            for result in pool.map(process_batch, batches):
                done.update(result)
                _CHECKPOINT.write_text(json.dumps(done, ensure_ascii=False), encoding="utf-8")
                print(f"  {len(done)}/{len(verbs)}", flush=True)
        # Audit every kept card once (marked so a resumed run skips it).
        unaudited = [
            r["entry"] for r in done.values() if r["status"] == "kept" and not r.get("audit_done")
        ]
        chunks = [unaudited[i : i + _AUDIT_BATCH] for i in range(0, len(unaudited), _AUDIT_BATCH)]
        print(f"auditing {len(unaudited)} cards in {len(chunks)} batches", flush=True)
        with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
            for chunk, changes in zip(chunks, pool.map(audit_batch, chunks), strict=True):
                for entry in chunk:
                    done[entry["id"]]["audit_done"] = True
                for vid, change in changes.items():
                    done[vid] = {**change, "audit_done": True}
                _CHECKPOINT.write_text(json.dumps(done, ensure_ascii=False), encoding="utf-8")
    except RuntimeError as exc:
        print(f"Bedrock failed ({exc}); progress saved, re-run to resume.", file=sys.stderr)
        return 1
    audited = sum(1 for r in done.values() if r.get("audited") or str(r.get("reason", "")).startswith("audit"))
    print(f"audit changed {audited} cards")

    for v in verbs:
        if v["verb"] in _EDITOR_DROP:
            done[v["id"]] = {"status": "dropped", "reason": "editor: " + _EDITOR_DROP[v["verb"]]}
    kept = [done[v["id"]]["entry"] for v in verbs if done[v["id"]]["status"] == "kept"]
    dropped = [
        {"id": v["id"], "verb": v["verb"], "reason": done[v["id"]]["reason"]}
        for v in verbs if done[v["id"]]["status"] == "dropped"
    ]
    fixed = sum(1 for v in verbs if done[v["id"]].get("fixed"))
    by_diff: dict[str, int] = {}
    for v in kept:
        by_diff[v["difficulty"]] = by_diff.get(v["difficulty"], 0) + 1
    print(f"kept {len(kept)} ({by_diff}), reviewer-fixed {fixed}, dropped {len(dropped)}")

    if args.dry_run:
        for v in kept[:15]:
            print(f"  {v['verb']:<14} {v['example'].replace(_BLANK, '[' + v['example_answer'] + ']')}")
        return 0
    if len(kept) < 300:
        print("Refusing to write: fewer than 300 verbs kept.", file=sys.stderr)
        return 1

    payload["verbs"] = kept
    payload["meta"] = {
        "source": "WithEnglishWeCan/generated-english-phrasal-verbs (verb list); "
                  "examples rewritten by scripts/rewrite_phrasal_examples.py",
        "count": len(kept),
        "by_difficulty": by_diff,
        "enriched": True,
        "glossed": len(kept),
        "rewritten": {"kept": len(kept), "reviewer_fixed": fixed, "dropped": len(dropped)},
    }
    _DATA.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _DROPPED.write_text(json.dumps(dropped, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {_DATA.relative_to(_REPO)} and {_DROPPED.relative_to(_REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
