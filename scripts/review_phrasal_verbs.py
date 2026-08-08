#!/usr/bin/env python3
"""Review + repair the phrasal-verb corpus with a stronger model (Opus).

The generator's Stage-2 enrichment (``generate_phrasal_verbs.py --enrich``) runs
Claude Haiku for speed. This pass grades every enriched verb with **Claude Opus
4.8** — a different, stronger model, so verification isn't the generator checking
its own homework. Opus judges four things per verb:

1. **gloss** — the Spanish gloss must actually mean the phrasal verb (a wrong or
   misleading translation is the most likely enrichment error).
2. **definitions** — at least one listed English sense must match how the verb is
   used in the example sentence (the source's senses/examples aren't aligned, so
   we only require *coverage*, not that every sense fits).
3. **difficulty** — the CEFR band should be roughly right (a wrong band is a
   minor issue, corrected, not a failure).
4. **example** — the blanked example must be a real, grammatical use of the verb.

**Fix in place, quarantine only if unfixable.** Opus returns corrections; we
apply a better gloss / difficulty / trimmed sense list directly. A verb is
**quarantined** (moved to ``phrasal_verbs.quarantine.json``, never loaded at
runtime) only when it's structurally broken — no sense matches the example, or
the example isn't a valid use — i.e. no in-place edit can save it.

**Fail closed.** A verb the model can't grade after retries is recorded as
``unreviewed`` and quarantined, never silently kept. ``meta.last_review`` records
counts so a commit can show the corpus was verified.

Usage::

    # Refresh creds first (or pass --auth):
    python scripts/review_phrasal_verbs.py --dry-run          # report only
    python scripts/review_phrasal_verbs.py --apply            # fix + quarantine
    python scripts/review_phrasal_verbs.py --apply --decisions dec.json

``--decisions`` JSON: ``{"keep": ["pv-0007"], "quarantine": ["pv-0100"]}`` —
human overrides that beat the model verdict.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bedrock import (  # local helper; sys.path set just above
    MODEL_OPUS,
    bedrock_auth,
    bedrock_converse,
    extract_json_array,
)

_REPO = Path(__file__).resolve().parent.parent
_DATA = _REPO / "activity" / "backend" / "app" / "games" / "data" / "phrasal_verbs.json"
_QUARANTINE = _DATA.with_name("phrasal_verbs.quarantine.json")

_BATCH = 25
_MAX_TOKENS = 4096
_TEMPERATURE = None  # Opus 4.8 rejects the deprecated temperature field
_VALID_DIFFICULTIES = {"beginner", "intermediate", "advanced"}


def _review_prompt(verbs: list[dict[str, Any]]) -> str:
    """Build the grading + repair instruction for one batch of verbs."""
    lines: list[str] = []
    for v in verbs:
        # Show the example with the blank filled, so Opus judges the real use.
        filled = v["example"].replace("___", f"[{v['example_answer']}]")
        lines.append(
            f'- id: {v["id"]}\n'
            f'  phrasal_verb: "{v["verb"]}"\n'
            f'  english_definitions: {json.dumps(v["definitions"], ensure_ascii=False)}\n'
            f'  spanish_gloss: "{v.get("gloss_es") or ""}"\n'
            f'  example_with_answer: "{filled}"\n'
            f'  difficulty: {v.get("difficulty", "?")}'
        )
    block = "\n".join(lines)
    return (
        "You are a meticulous bilingual (Spanish/English) editor reviewing "
        "English phrasal-verb flashcards for Spanish-speaking learners. Each "
        "card lists the verb, its English definitions (multiple senses, NOT "
        "aligned to the example), a Spanish gloss, and one example sentence with "
        "the verb shown in [brackets].\n\n"
        "Grade EACH card:\n"
        "1. gloss — the Spanish gloss must correctly translate the phrasal "
        "verb's meaning. A wrong/misleading gloss is the main failure to catch. "
        "If it's off, provide a corrected short gloss (1-6 words, senses "
        "separated by commas).\n"
        "2. definitions — at least ONE english_definition should match how the "
        "verb is used in the example. IMPORTANT: the source's senses are often "
        "incomplete, so if none matches, DO NOT condemn the card — instead "
        "provide the missing sense in suggested_definition (a short English "
        "definition of the verb AS USED in the example). This is the common "
        "case, not a failure.\n"
        "3. difficulty — beginner/intermediate/advanced by everyday usefulness "
        "for a learner. A wrong label is minor: return the corrected one.\n\n"
        "Decide a verdict (prefer 'fix' over 'broken' — quarantining loses a "
        "useful verb, so reserve 'broken' for genuinely unsalvageable cards):\n"
        '- "ok" — gloss correct, difficulty fine, and a listed definition '
        "matches the example.\n"
        '- "fix" — usable but needs a better gloss, a corrected difficulty, '
        "and/or a missing definition added (fill the suggested_* fields). Use "
        "this whenever the only problem is metadata — including when the "
        "example uses a sense not yet listed.\n"
        '- "broken" — ONLY if the example sentence is not a real, grammatical '
        "use of this phrasal verb at all (garbled, wrong verb, nonsensical). A "
        "mismatch between listed senses and the example is 'fix', never "
        '"broken".\n\n'
        f"Cards:\n{block}\n\n"
        "Return ONLY a JSON array, no prose, no markdown fences. One object per "
        'card: {"id":"<id>","verdict":"ok"|"fix"|"broken","reasons":["short",...],'
        '"suggested_gloss":"<corrected gloss or empty>",'
        '"suggested_difficulty":"beginner"|"intermediate"|"advanced"|"",'
        '"suggested_definition":"<missing sense as used in the example, or empty>"}'
    )


def _load_corpus() -> dict[str, Any]:
    if not _DATA.exists():
        print(f"corpus not found: {_DATA} (run the generator first)", file=sys.stderr)
        raise SystemExit(1)
    return json.loads(_DATA.read_text(encoding="utf-8"))


def _load_decisions(path: str | None) -> tuple[set[str], set[str]]:
    if not path:
        return set(), set()
    p = Path(path)
    if not p.exists():
        print(f"decisions file not found: {p}", file=sys.stderr)
        raise SystemExit(1)
    data = json.loads(p.read_text(encoding="utf-8"))
    return {str(x) for x in data.get("keep", [])}, {str(x) for x in data.get("quarantine", [])}


class _BedrockUnavailable(Exception):
    """A batch failed at the Bedrock call (e.g. expired creds), not at parsing.

    Distinct from an empty parse: the caller must ABORT on this rather than
    treat the batch's verbs as unreviewed — otherwise an expiry mid-run would
    silently quarantine every remaining verb (mass data loss). Re-run to resume.
    """


def _review_batch(verbs: list[dict[str, Any]], model: str, verbose: bool) -> dict[str, dict]:
    """Grade one batch; return {id: verdict-dict}. Empty on unparseable response.

    Raises :class:`_BedrockUnavailable` if the Bedrock call itself fails, so the
    caller can stop instead of mass-quarantining. Ids missing from a *parsed*
    return are treated as ``unreviewed`` by the caller (fail closed).
    """
    try:
        text = bedrock_converse(
            _review_prompt(verbs), model=model, max_tokens=_MAX_TOKENS, temperature=_TEMPERATURE,
        )
    except RuntimeError as exc:
        raise _BedrockUnavailable(str(exc)) from exc
    verdicts: dict[str, dict] = {}
    for item in extract_json_array(text):
        if not isinstance(item, dict):
            continue
        cid = item.get("id")
        verdict = item.get("verdict")
        if not isinstance(cid, str) or verdict not in ("ok", "fix", "broken"):
            continue
        reasons = item.get("reasons")
        gloss = item.get("suggested_gloss")
        diff = item.get("suggested_difficulty")
        sdef = item.get("suggested_definition")
        verdicts[cid] = {
            "verdict": verdict,
            "reasons": [r for r in reasons if isinstance(r, str)] if isinstance(reasons, list) else [],
            "suggested_gloss": gloss.strip() if isinstance(gloss, str) else "",
            "suggested_difficulty": diff if diff in _VALID_DIFFICULTIES else "",
            "suggested_definition": sdef.strip() if isinstance(sdef, str) else "",
        }
    if verbose:
        counts = {"ok": 0, "fix": 0, "broken": 0}
        for v in verdicts.values():
            counts[v["verdict"]] += 1
        print(f"  · batch {len(verbs)} → {counts}, {len(verbs) - len(verdicts)} unreviewed")
    return verdicts


def main() -> int:
    parser = argparse.ArgumentParser(description="Review + repair the phrasal corpus with Opus.")
    parser.add_argument("--model", default=MODEL_OPUS, help=f"Bedrock model (default {MODEL_OPUS})")
    parser.add_argument("--apply", action="store_true", help="Apply fixes + quarantine (writes files).")
    parser.add_argument("--dry-run", action="store_true", help="Report only; change nothing.")
    parser.add_argument("--limit", type=int, default=0, help="Review only the first N verbs (debug).")
    parser.add_argument("--decisions", default=None, help='Overrides: {"keep":[ids],"quarantine":[ids]}')
    parser.add_argument("--auth", action="store_true", help="Refresh Bedrock creds first.")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    if args.apply == args.dry_run:
        print("Choose exactly one of --apply or --dry-run.", file=sys.stderr)
        return 2

    if args.auth:
        bedrock_auth()

    force_keep, force_quarantine = _load_decisions(args.decisions)
    payload = _load_corpus()
    verbs: list[dict[str, Any]] = payload["verbs"]
    if args.limit > 0:
        verbs = verbs[: args.limit]

    to_review = [v for v in verbs if v["id"] not in force_keep and v["id"] not in force_quarantine]
    verdicts: dict[str, dict] = {}
    for start in range(0, len(to_review), _BATCH):
        batch = to_review[start : start + _BATCH]
        try:
            verdicts.update(_review_batch(batch, args.model, args.verbose))
        except _BedrockUnavailable as exc:
            # Abort rather than let the remaining verbs fall through as
            # "unreviewed → quarantined" — an expiry mid-run would otherwise
            # silently cull the whole tail. Nothing is written; re-run to retry.
            done = start
            print(
                f"\nBedrock unavailable after {done}/{len(to_review)} reviewed "
                f"({exc}). Aborting WITHOUT writing so no verbs are wrongly "
                f"quarantined. Refresh creds and re-run.",
                file=sys.stderr,
            )
            return 1
        print(f"  reviewed {min(start + _BATCH, len(to_review))}/{len(to_review)}", file=sys.stderr)

    # Classify every verb.
    fixed: list[str] = []
    quarantined: list[dict[str, Any]] = []
    unreviewed: list[str] = []
    survivors: list[dict[str, Any]] = []

    for v in verbs:
        vid = v["id"]
        if vid in force_quarantine:
            quarantined.append(v)
            continue
        if vid in force_keep:
            survivors.append(v)
            continue
        verdict = verdicts.get(vid)
        if verdict is None:
            # Fail closed: unverifiable → quarantine.
            unreviewed.append(vid)
            quarantined.append(v)
            continue
        if verdict["verdict"] == "broken":
            quarantined.append(v)
            continue
        if verdict["verdict"] == "fix":
            if verdict["suggested_gloss"]:
                v["gloss_es"] = verdict["suggested_gloss"]
            if verdict["suggested_difficulty"]:
                v["difficulty"] = verdict["suggested_difficulty"]
            # Add a missing sense (the example's meaning) if the model supplied
            # one and it isn't already present — this is the alignment repair.
            sdef = verdict["suggested_definition"]
            if sdef and sdef.lower() not in {d.lower() for d in v["definitions"]}:
                # Lead with the example's sense so the exercise hint matches.
                v["definitions"] = [sdef, *v["definitions"]][:4]
            fixed.append(vid)
        survivors.append(v)

    report = {
        "reviewed": len(to_review),
        "ok": sum(1 for x in verdicts.values() if x["verdict"] == "ok"),
        "fixed": len(fixed),
        "broken": sum(1 for x in verdicts.values() if x["verdict"] == "broken"),
        "unreviewed_quarantined": len(unreviewed),
        "quarantined_total": len(quarantined),
        "survivors": len(survivors),
    }
    print(json.dumps(report, indent=2))

    if args.dry_run:
        print("(dry run) no files written.")
        return 0

    # Recompute difficulty spread from survivors.
    by_diff: dict[str, int] = {}
    for v in survivors:
        by_diff[v["difficulty"]] = by_diff.get(v["difficulty"], 0) + 1

    payload["verbs"] = survivors
    payload["meta"]["count"] = len(survivors)
    payload["meta"]["by_difficulty"] = by_diff
    payload["meta"]["glossed"] = sum(1 for v in survivors if v.get("gloss_es"))
    payload["meta"]["last_review"] = {
        "model": args.model,
        "survivors_all_passed": len(unreviewed) == 0,
        **report,
    }
    _DATA.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Merge newly-quarantined verbs into the sidecar (never delete).
    if quarantined:
        existing: list[dict[str, Any]] = []
        if _QUARANTINE.exists():
            existing = json.loads(_QUARANTINE.read_text(encoding="utf-8")).get("verbs", [])
        seen = {v["id"] for v in existing}
        existing.extend(v for v in quarantined if v["id"] not in seen)
        _QUARANTINE.write_text(
            json.dumps({"verbs": existing}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Quarantined {len(quarantined)} verbs -> {_QUARANTINE.relative_to(_REPO)}")

    print(f"Wrote {len(survivors)} verbs ({by_diff}) -> {_DATA.relative_to(_REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
