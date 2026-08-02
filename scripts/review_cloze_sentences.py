#!/usr/bin/env python3
"""Offline verification pass for the committed cloze cards.

The generator (``generate_cloze_sentences.py``) uses Claude Haiku for cheap
bulk content. This reviewer is the **second opinion**: it grades every card in
the committed ``cloze_sentences.json`` with a *stronger* model (Claude Opus 4.8
by default), so verification isn't the same model checking its own homework.

Each card is graded on the things a machine check can't catch:

* **translation** — do the target and context sentences actually mean the same?
* **answer** — is the blanked ``answer`` the correct, natural word for the gap,
  with correct grammar (tense/mood/agreement, incl. subjunctive triggers)?
* **distractors** — is each distractor clearly WRONG (not a synonym, not an
  equally-valid alternative), so there's exactly one right answer?
* **difficulty** — is the assigned band roughly right?

The reviewer returns a verdict per card (``ok`` / ``suspect``) with reasons.
Suspects are **quarantined**: moved out of ``cloze_sentences.json`` into a
sibling ``cloze_sentences.quarantine.json`` for human review, so the shipped
corpus contains only cards that passed both the generator's structural checks
and this semantic review. A human can then fix + reinstate quarantined cards, or
approve/override verdicts via a decisions file.

Usage::

    # Review the whole corpus, write a report, DON'T modify anything:
    python scripts/review_cloze_sentences.py --dry-run

    # Review and quarantine suspects into the sidecar file:
    python scripts/review_cloze_sentences.py --quarantine

    # Review only a sample (fast spot-check):
    python scripts/review_cloze_sentences.py --limit 40 --dry-run

    # Human override: force-keep or force-quarantine specific ids regardless of
    # the model's verdict (JSON: {"keep": ["es-0007"], "quarantine": ["en-0100"]}).
    python scripts/review_cloze_sentences.py --quarantine --decisions decisions.json

The reviewer **never deletes** a card: quarantined cards are preserved in the
sidecar with the reviewer's reasons, and can be re-merged after fixing with
``generate_cloze_sentences.py --merge`` or by hand.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from _bedrock import (
    MODEL_OPUS,
    bedrock_auth,
    bedrock_converse,
    extract_json_array,
)

_REPO = Path(__file__).resolve().parent.parent
_DATA = _REPO / "activity" / "backend" / "app" / "games" / "data" / "cloze_sentences.json"
_QUARANTINE = _DATA.with_name("cloze_sentences.quarantine.json")

#: Cards to grade per review call. Smaller than generation batches because the
#: reviewer reasons about each card and returns structured per-card verdicts;
#: keeping it modest bounds output tokens and makes a re-try cheap.
_BATCH = 12

#: Review is a judgement task. Opus 4.8 deprecates the temperature field and
#: errors if it's sent, so we omit it (None) rather than pass a value.
_MAX_TOKENS = 4096
_TEMPERATURE = None

_LANG_NAMES = {"es": "Spanish", "en": "English"}


def _review_prompt(cards: list[dict[str, Any]]) -> str:
    """Build the grading instruction for one batch of cards.

    The card is presented with its blank filled by the answer (so the reviewer
    judges the *intended* sentence) plus the answer and distractors called out.
    We ask for a strict JSON array of verdicts keyed by id.
    """
    lines: list[str] = []
    for c in cards:
        target_name = _LANG_NAMES.get(c.get("target", ""), c.get("target", "?"))
        filled = c["cloze"].replace("___", f"[{c['answer']}]")
        lines.append(
            f'- id: {c["id"]}\n'
            f'  target_language: {target_name}\n'
            f'  sentence_with_answer: "{filled}"\n'
            f'  context_translation: "{c["context"]}"\n'
            f'  answer: "{c["answer"]}"\n'
            f'  distractors: {json.dumps(c["distractors"], ensure_ascii=False)}\n'
            f'  difficulty: {c.get("difficulty", "?")}'
        )
    cards_block = "\n".join(lines)

    return (
        "You are a meticulous bilingual (Spanish/English) language-teaching "
        "editor reviewing fill-in-the-blank flashcards for correctness. The "
        "blank is shown filled with the intended answer in [brackets].\n\n"
        "Grade EACH card on:\n"
        "1. translation — the sentence and its context_translation must mean the "
        "same thing.\n"
        "2. answer — the bracketed answer must be the correct, natural word for "
        "the blank, grammatically correct (tense, mood, number, gender; honour "
        "subjunctive triggers like 'dudo que', 'es posible que', 'para que').\n"
        "3. distractors — EACH distractor must be clearly WRONG in the sentence: "
        "NOT a synonym or near-synonym of the answer, and NOT an equally valid "
        "alternative. Exactly one word (the answer) may correctly fill the gap.\n"
        "4. difficulty — the label (beginner/intermediate/advanced) should be "
        "roughly appropriate; a wrong label is a minor issue, not a failure.\n\n"
        "A card is \"suspect\" if translation or answer is wrong, or if any "
        "distractor is a synonym/valid alternative. Difficulty mismatch alone is "
        "NOT suspect (note it in reasons instead).\n\n"
        f"Cards:\n{cards_block}\n\n"
        "Return ONLY a JSON array, no prose, no markdown fences. One object per "
        'card: {"id":"<id>","verdict":"ok"|"suspect","reasons":["short reason", '
        '...],"suggested_answer":"<if the answer is wrong, the correct word, else '
        'empty>"}'
    )


def _load_corpus() -> dict[str, Any]:
    if not _DATA.exists():
        print(f"content file not found: {_DATA}", file=sys.stderr)
        raise SystemExit(1)
    return json.loads(_DATA.read_text(encoding="utf-8"))


def _load_decisions(path: str | None) -> tuple[set[str], set[str]]:
    """Load human overrides: (force_keep_ids, force_quarantine_ids)."""
    if not path:
        return set(), set()
    p = Path(path)
    if not p.exists():
        print(f"decisions file not found: {p}", file=sys.stderr)
        raise SystemExit(1)
    data = json.loads(p.read_text(encoding="utf-8"))
    keep = {str(x) for x in data.get("keep", [])}
    quarantine = {str(x) for x in data.get("quarantine", [])}
    return keep, quarantine


def _review_batch(cards: list[dict[str, Any]], model: str, verbose: bool) -> dict[str, dict]:
    """Grade one batch; return {id: {verdict, reasons, suggested_answer}}.

    On a transient failure or unparseable response, returns an empty dict for
    the batch (the caller records those ids as ``unreviewed`` — never silently
    treated as ``ok``).
    """
    prompt = _review_prompt(cards)
    try:
        text = bedrock_converse(
            prompt, model=model, max_tokens=_MAX_TOKENS, temperature=_TEMPERATURE,
        )
    except RuntimeError as exc:
        print(f"  ! review batch failed: {exc}", file=sys.stderr)
        return {}
    items = extract_json_array(text)
    verdicts: dict[str, dict] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        cid = item.get("id")
        verdict = item.get("verdict")
        if not isinstance(cid, str) or verdict not in ("ok", "suspect"):
            continue
        reasons = item.get("reasons")
        verdicts[cid] = {
            "verdict": verdict,
            "reasons": [r for r in reasons if isinstance(r, str)] if isinstance(reasons, list) else [],
            "suggested_answer": item.get("suggested_answer") if isinstance(item.get("suggested_answer"), str) else "",
        }
    if verbose:
        ok = sum(1 for v in verdicts.values() if v["verdict"] == "ok")
        print(f"  · batch {len(cards)} cards → {ok} ok, {len(verdicts) - ok} suspect, "
              f"{len(cards) - len(verdicts)} unreviewed")
    return verdicts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model", default=MODEL_OPUS,
        help=f"Bedrock model id for the review pass (default: {MODEL_OPUS})",
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="review only the first N cards (0 = all); for a fast spot-check",
    )
    parser.add_argument(
        "--quarantine", action="store_true",
        help="move suspect cards out of the corpus into the sidecar file",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="review + report only; never modify the corpus (default behaviour)",
    )
    parser.add_argument(
        "--decisions", default=None,
        help='JSON of human overrides: {"keep": [ids], "quarantine": [ids]}',
    )
    parser.add_argument(
        "--report", default=None,
        help="write the full per-card verdict report to this JSON path",
    )
    parser.add_argument(
        "--no-auth", action="store_true",
        help="skip the `ada credentials update` refresh",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    if args.quarantine and args.dry_run:
        print("--quarantine and --dry-run are mutually exclusive.", file=sys.stderr)
        return 1

    corpus = _load_corpus()
    cards: list[dict[str, Any]] = corpus.get("cards", [])
    if not cards:
        print("corpus has no cards.", file=sys.stderr)
        return 1
    force_keep, force_quarantine = _load_decisions(args.decisions)

    review_cards = cards[: args.limit] if args.limit > 0 else cards
    print(
        f"Reviewing {len(review_cards)} of {len(cards)} cards with {args.model} "
        f"(batch {_BATCH})…"
    )

    if not args.no_auth:
        print("Refreshing Bedrock credentials (bedrock-how)…")
        bedrock_auth()

    verdicts: dict[str, dict] = {}
    for i in range(0, len(review_cards), _BATCH):
        batch = review_cards[i : i + _BATCH]
        verdicts.update(_review_batch(batch, args.model, args.verbose))
        time.sleep(0.4)  # gentle pacing

    # Classify. A card the model didn't return a verdict for is "unreviewed" —
    # surfaced explicitly, never assumed OK.
    ok_ids: list[str] = []
    suspect: list[dict[str, Any]] = []
    unreviewed: list[str] = []
    for c in review_cards:
        cid = c["id"]
        # Human overrides win over the model.
        if cid in force_quarantine:
            suspect.append({**c, "_review": {"verdict": "suspect", "reasons": ["human override"], "suggested_answer": ""}})
            continue
        if cid in force_keep:
            ok_ids.append(cid)
            continue
        v = verdicts.get(cid)
        if v is None:
            unreviewed.append(cid)
        elif v["verdict"] == "suspect":
            suspect.append({**c, "_review": v})
        else:
            ok_ids.append(cid)

    # ── report ──────────────────────────────────────────────────────────────
    print("\n=== Review summary ===")
    print(f"  ok:         {len(ok_ids)}")
    print(f"  suspect:    {len(suspect)}")
    print(f"  unreviewed: {len(unreviewed)}")
    if suspect:
        print("\nSuspect cards:")
        for s in suspect[:50]:
            r = "; ".join(s["_review"]["reasons"]) or "(no reason given)"
            sug = s["_review"].get("suggested_answer")
            sug_txt = f'  → suggested: {sug}' if sug else ""
            print(f"  - {s['id']} [{s.get('target')}/{s.get('difficulty')}] "
                  f"answer={s['answer']!r}: {r}{sug_txt}")
        if len(suspect) > 50:
            print(f"  … and {len(suspect) - 50} more")
    if unreviewed:
        print(f"\nUnreviewed (model gave no verdict): {unreviewed[:20]}"
              f"{' …' if len(unreviewed) > 20 else ''}")

    if args.report:
        report = {
            "meta": {
                "model": args.model,
                "reviewed_at": datetime.now(UTC).isoformat(),
                "reviewed": len(review_cards),
                "ok": len(ok_ids),
                "suspect": len(suspect),
                "unreviewed": len(unreviewed),
            },
            "suspect": [{"id": s["id"], **s["_review"]} for s in suspect],
            "unreviewed": unreviewed,
        }
        Path(args.report).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
        print(f"\nWrote report -> {args.report}")

    # ── quarantine ────────────────────────────────────────────────────────────
    if not args.quarantine:
        print("\n(dry-run: corpus unchanged. Re-run with --quarantine to remove suspects.)")
        return 0

    if not suspect:
        print("\nNo suspects to quarantine. Corpus unchanged.")
        return 0

    suspect_ids = {s["id"] for s in suspect}
    kept = [c for c in cards if c["id"] not in suspect_ids]

    # Append to any existing quarantine sidecar (don't clobber prior batches).
    existing_q: list[dict[str, Any]] = []
    if _QUARANTINE.exists():
        try:
            existing_q = json.loads(_QUARANTINE.read_text(encoding="utf-8")).get("cards", [])
        except (json.JSONDecodeError, AttributeError):
            existing_q = []
    q_seen = {c["id"] for c in existing_q}
    quarantined_now = [
        {k: v for k, v in s.items()} for s in suspect if s["id"] not in q_seen
    ]

    # Recompute the corpus counts/meta after removal.
    counts: dict[str, int] = {}
    for c in kept:
        bucket = f"{c['target']}/{c['difficulty']}"
        counts[bucket] = counts.get(bucket, 0) + 1
    corpus["cards"] = kept
    corpus.setdefault("meta", {})
    corpus["meta"]["counts"] = counts
    corpus["meta"]["total"] = len(kept)
    corpus["meta"]["last_review"] = {
        "model": args.model,
        "reviewed_at": datetime.now(UTC).isoformat(),
        "quarantined": len(quarantined_now),
    }

    _DATA.write_text(json.dumps(corpus, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _QUARANTINE.write_text(
        json.dumps(
            {
                "meta": {
                    "note": "Cards quarantined by review_cloze_sentences.py — fix and "
                            "re-merge, or discard. NOT loaded by the runtime.",
                    "updated_at": datetime.now(UTC).isoformat(),
                },
                "cards": existing_q + quarantined_now,
            },
            ensure_ascii=False, indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    print(f"\nQuarantined {len(quarantined_now)} card(s):")
    print(f"  corpus now {len(kept)} cards -> {_DATA.relative_to(_REPO)}")
    print(f"  quarantine {len(existing_q) + len(quarantined_now)} cards -> "
          f"{_QUARANTINE.relative_to(_REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
