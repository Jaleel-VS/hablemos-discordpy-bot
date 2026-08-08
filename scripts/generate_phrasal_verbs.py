#!/usr/bin/env python3
"""Build the phrasal-verb corpus for the Activity "phrasal" game.

The source is the community dataset
https://github.com/WithEnglishWeCan/generated-english-phrasal-verbs
(``phrasal.verbs.build.json``): ~3350 phrasal verbs keyed by phrase, each with
``descriptions`` (definitions), ``examples``, ``derivatives`` (inflected forms),
``synonyms``, a coarse ``frequency`` int, and a ``translations`` blob (Russian —
dropped). 3350 is far too many and mostly obscure, so this script curates.

Two stages, mirroring the cloze pipeline (generate → review), so the game ships
playable with **no LLM** and gets enriched later:

* **Stage 1 — filter (no network).** Keep only entries with a usable definition
  and at least one example that actually contains the verb (so we can build a
  fill-in-the-blank), score them by ``frequency`` + a curated common-particle /
  common-verb heuristic, and take the top ``--limit``. Emits a fully playable
  corpus: English definitions, particle + whole-verb blank modes, and
  multiple-choice distractors drawn from other verbs' particles / phrases.
  This is the default and needs nothing but the source file.

* **Stage 2 — enrich (Bedrock, ``--enrich``).** For the filtered set, ask Claude
  for a CEFR difficulty band, a short Spanish gloss of the definition, and a
  usefulness keep/drop — then (optionally) an Opus review pass. Needs the
  ``bedrock-how`` AWS profile (same path as generate_cloze_sentences.py). The
  runtime NEVER calls an LLM; this only runs offline and commits JSON.

Output: ``activity/backend/app/games/data/phrasal_verbs.json``

Shape::

    {
      "meta": {"generated_at": "...", "source": "...", "counts": {...},
               "enriched": false},
      "difficulties": {"beginner": "Beginner", ...},
      "verbs": [
        {
          "id": "pv-0001",
          "verb": "look up",
          "particle": "up",
          "base": "look",
          "definitions": ["to search for information"],  # all senses (unaligned)
          "gloss_es": null,               # filled by --enrich
          "example": "You can ___ the word in a dictionary.",
          "example_answer": "look up",    # the form that filled the blank
          "forms": ["look up", "looks up", "looking up", "looked up"],
          "distractors_particle": ["down", "out", "over"],
          "difficulty": "intermediate",
          "frequency": 4
        },
        ...
      ]
    }

Usage::

    # Stage 1 — playable corpus, no network:
    python scripts/generate_phrasal_verbs.py --source /path/to/phrasal.verbs.build.json --limit 400

    # Stage 2 — enrich the committed corpus with CEFR + Spanish glosses:
    python scripts/generate_phrasal_verbs.py --enrich --auth

The script fails loudly (exit 1, no write) if too few verbs survive filtering,
so a bad source can't silently ship a tiny pool. ``--dry-run`` reports without
writing.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parent.parent
_OUT = _REPO / "activity" / "backend" / "app" / "games" / "data" / "phrasal_verbs.json"

# Common English particles/prepositions that form phrasal verbs. Used both to
# detect the particle in a phrase and as the multiple-choice distractor pool.
_PARTICLES = [
    "up", "down", "in", "out", "on", "off", "over", "back", "away", "around",
    "about", "along", "through", "across", "by", "for", "into", "onto", "with",
    "after", "ahead", "apart", "aside", "forward", "together", "under", "up to",
    "down on", "out of", "in on", "away with", "up with", "out for",
]
# Longest-first so "out of" matches before "out".
_PARTICLES_BY_LEN = sorted(set(_PARTICLES), key=lambda p: -len(p))

# High-utility base verbs — a phrase built on one of these is more likely to be
# worth teaching. A light heuristic, not gospel; Stage 2 refines usefulness.
_COMMON_BASES = {
    "get", "go", "come", "take", "put", "give", "make", "look", "turn", "bring",
    "break", "call", "carry", "check", "cut", "fall", "fill", "find",
    "hold", "keep", "let", "move", "pick", "point", "pull", "push", "run", "set",
    "show", "sit", "stand", "start", "stay", "switch", "throw", "try", "wake",
    "walk", "work", "back", "blow", "catch", "clear", "close", "count", "draw",
    "dress", "drop", "eat", "figure", "hand", "hang", "head", "leave", "live",
    "log", "pass", "pay", "play", "read", "ring", "send", "settle", "sign",
    "sort", "speak", "split", "step", "stick", "tear", "tell", "think", "warm",
    "wear", "write",
}

_DIFFICULTIES = {
    "beginner": "Beginner",
    "intermediate": "Intermediate",
    "advanced": "Advanced",
}
_VALID_DIFFICULTIES = set(_DIFFICULTIES)
_BLANK = "___"


def _split_particle(verb: str) -> tuple[str, str]:
    """Split a phrase into (base, particle). Particle is the trailing token(s).

    Falls back to (whole phrase, "") when no known particle trails — such
    entries are dropped in Stage 1 (we can't build a particle-blank from them).
    """
    v = verb.strip().lower()
    for part in _PARTICLES_BY_LEN:
        suffix = " " + part
        if v.endswith(suffix) and len(v) > len(suffix):
            return v[: -len(suffix)].strip(), part
    return v, ""


def _build_blank(example: str, forms: list[str]) -> tuple[str, str] | None:
    """Blank the first occurrence of any verb form in *example*.

    Returns (clozed_example, matched_form) or None if no form appears as a
    whole-word span (so the game can always reconstruct the answer).
    """
    lowered = example.lower()
    # Try the longest forms first so "looked up" wins over "looked".
    for form in sorted(forms, key=lambda f: -len(f)):
        pattern = re.compile(rf"\b{re.escape(form.lower())}\b")
        m = pattern.search(lowered)
        if m:
            start, end = m.span()
            return example[:start] + _BLANK + example[end:], example[start:end]
    return None


def _score(entry: dict[str, Any], base: str, particle: str) -> int:
    """Heuristic usefulness score for Stage 1 ranking (higher = keep)."""
    score = 0
    freq = entry.get("frequency")
    if isinstance(freq, int):
        score += freq * 2  # the source's own signal, weighted
    if base in _COMMON_BASES:
        score += 5
    # A common single-word particle is more "phrasal-verb-like" than a rare
    # multiword preposition tail.
    if particle and " " not in particle:
        score += 2
    # Reward richer entries (more definitions/examples/synonyms = better teach).
    score += min(len(entry.get("examples", [])), 3)
    score += min(len(entry.get("synonyms", [])), 3)
    return score


def _usable_definitions(entry: dict[str, Any], *, cap: int = 4) -> list[str]:
    """All non-empty, reasonably short definitions (senses), capped.

    The source lists multiple senses and multiple examples that are NOT
    index-aligned, so we keep every usable sense. Showing all of them means the
    sense the example uses is always among those displayed — the alternative
    (one arbitrary sense) can contradict the example for polysemous verbs like
    "give up" or "make up". Sense-ranking/alignment is left to Stage 2 (LLM).
    """
    out: list[str] = []
    seen: set[str] = set()
    for d in entry.get("descriptions", []):
        if not isinstance(d, str):
            continue
        text = d.strip()
        key = text.lower()
        if 3 <= len(text) <= 200 and key not in seen:
            out.append(text)
            seen.add(key)
        if len(out) >= cap:
            break
    return out


def _forms(verb: str, entry: dict[str, Any]) -> list[str]:
    """Accepted answer forms: the phrase plus its inflected derivatives."""
    forms = {verb.strip().lower()}
    for d in entry.get("derivatives", []):
        if isinstance(d, str) and d.strip():
            forms.add(d.strip().lower())
    return sorted(forms)


def stage1_filter(source: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    """Curate the raw source into a ranked, playable verb list (no network)."""
    candidates: list[tuple[int, dict[str, Any]]] = []

    for verb, entry in source.items():
        if not isinstance(entry, dict) or not isinstance(verb, str):
            continue
        definitions = _usable_definitions(entry)
        if not definitions:
            continue
        base, particle = _split_particle(verb)
        if not particle:
            continue  # can't build a particle-blank; skip non-particle phrases
        forms = _forms(verb, entry)

        # Need at least one example that actually contains a verb form.
        clozed: tuple[str, str] | None = None
        for ex in entry.get("examples", []):
            if not isinstance(ex, str) or not ex.strip():
                continue
            clozed = _build_blank(ex.strip(), forms)
            if clozed is not None:
                break
        if clozed is None:
            continue

        example, example_answer = clozed
        raw_freq = entry.get("frequency")
        freq: int = raw_freq if isinstance(raw_freq, int) else 0
        candidates.append((
            _score(entry, base, particle),
            {
                "verb": verb.strip().lower(),
                "particle": particle,
                "base": base,
                "definitions": definitions,
                "gloss_es": None,
                "example": example,
                "example_answer": example_answer,
                "forms": forms,
                "difficulty": _heuristic_difficulty(freq, base),
                "frequency": freq,
            },
        ))

    # Rank by score desc, then stable by verb for reproducibility.
    candidates.sort(key=lambda t: (-t[0], t[1]["verb"]))
    chosen = [c for _, c in candidates[:limit]]

    _attach_particle_distractors(chosen)
    for i, v in enumerate(chosen, 1):
        v["id"] = f"pv-{i:04d}"
    return chosen


def _heuristic_difficulty(freq: int, base: str) -> str:
    """Crude CEFR-ish bucket from the source frequency + common-base signal.

    Stage 2 (--enrich) overwrites this with a model judgment; this keeps the
    no-LLM corpus usable.
    """
    if freq >= 5 or base in _COMMON_BASES:
        return "beginner"
    if freq >= 2:
        return "intermediate"
    return "advanced"


def _attach_particle_distractors(verbs: list[dict[str, Any]]) -> None:
    """Give each verb 3 particle distractors (for particle-blank MC mode)."""
    for v in verbs:
        answer = v["particle"]
        pool = [p for p in _PARTICLES if p != answer and " " not in p]
        # Deterministic pick by hashing the verb (no global RNG; reproducible).
        import hashlib

        digest = hashlib.sha256(v["verb"].encode()).digest()
        picks: list[str] = []
        i = 0
        while len(picks) < 3 and i < len(digest) * 2:
            cand = pool[digest[i % len(digest)] % len(pool)]
            if cand not in picks:
                picks.append(cand)
            i += 1
        v["distractors_particle"] = picks


def _write(verbs: list[dict[str, Any]], *, enriched: bool, dry_run: bool) -> None:
    """Write the corpus JSON (or print a summary for --dry-run)."""
    by_diff: dict[str, int] = {}
    for v in verbs:
        by_diff[v["difficulty"]] = by_diff.get(v["difficulty"], 0) + 1

    payload = {
        "meta": {
            "source": "WithEnglishWeCan/generated-english-phrasal-verbs",
            "count": len(verbs),
            "by_difficulty": by_diff,
            "enriched": enriched,
        },
        "difficulties": _DIFFICULTIES,
        "verbs": verbs,
    }
    if dry_run:
        print(json.dumps(payload["meta"], indent=2))
        print(f"(dry run) would write {len(verbs)} verbs to {_OUT.relative_to(_REPO)}")
        return
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(verbs)} verbs ({by_diff}) -> {_OUT.relative_to(_REPO)}")


def main() -> int:
    p = argparse.ArgumentParser(description="Build the phrasal-verb game corpus.")
    p.add_argument(
        "--source", type=Path, required=False,
        help="Path to phrasal.verbs.build.json (Stage 1 input).",
    )
    p.add_argument("--limit", type=int, default=400, help="Max verbs to keep (default 400).")
    p.add_argument(
        "--min", type=int, default=100,
        help="Fail if fewer than this many verbs survive (default 100).",
    )
    p.add_argument(
        "--enrich", action="store_true",
        help="Stage 2: enrich the committed corpus via Bedrock (CEFR + ES gloss).",
    )
    p.add_argument(
        "--model", default="haiku", choices=("haiku", "opus"),
        help="Enrich model: 'haiku' (fast/cheap, default) or 'opus' (stronger).",
    )
    p.add_argument("--auth", action="store_true", help="Refresh Bedrock creds first (--enrich).")
    p.add_argument("--dry-run", action="store_true", help="Report without writing.")
    args = p.parse_args()

    if args.enrich:
        return _run_enrich(auth=args.auth, dry_run=args.dry_run, model_key=args.model)

    if not args.source or not args.source.exists():
        print("Stage 1 needs --source pointing at phrasal.verbs.build.json", file=sys.stderr)
        return 1

    source = json.loads(args.source.read_text(encoding="utf-8"))
    if not isinstance(source, dict):
        print("source JSON must be an object keyed by phrase", file=sys.stderr)
        return 1

    verbs = stage1_filter(source, args.limit)
    if len(verbs) < args.min:
        print(
            f"Only {len(verbs)} verbs survived filtering (need >= {args.min}). "
            "Not writing.",
            file=sys.stderr,
        )
        return 1

    _write(verbs, enriched=False, dry_run=args.dry_run)
    return 0


def _run_enrich(*, auth: bool, dry_run: bool, model_key: str = "haiku") -> int:
    """Stage 2: add CEFR difficulty + Spanish gloss to the committed corpus.

    Imported lazily so Stage 1 has no dependency on the Bedrock helper.
    ``model_key`` selects Haiku (fast/cheap) or Opus (stronger, slower).
    """
    if not _OUT.exists():
        print(f"No corpus at {_OUT} — run Stage 1 first.", file=sys.stderr)
        return 1

    sys.path.insert(0, str(_REPO / "scripts"))
    import _bedrock  # local helper, imported lazily so Stage 1 has no dep on it

    if auth:
        _bedrock.bedrock_auth()

    model = _bedrock.MODEL_OPUS if model_key == "opus" else _bedrock.MODEL_HAIKU
    # Opus 4.8 rejects the deprecated temperature field; Opus is also slower, so
    # use a smaller batch to keep each request bounded.
    temperature = None if model_key == "opus" else 0.4
    batch_size = 25 if model_key == "opus" else 40
    print(f"Enriching with {model} (batch {batch_size})", file=sys.stderr)

    payload = json.loads(_OUT.read_text(encoding="utf-8"))
    verbs: list[dict[str, Any]] = payload["verbs"]
    by_id = {v["id"]: v for v in verbs}

    def _checkpoint() -> None:
        """Persist current progress so a mid-run failure isn't total loss.

        Opus over hundreds of verbs outlasts nothing in particular, but the
        Bedrock creds expire (~1h); without this, an expiry near the end
        discards every enriched verb. We write after each batch and mark
        ``enriched`` only once the whole pass completes.
        """
        by_diff = {}
        for v in verbs:
            by_diff[v["difficulty"]] = by_diff.get(v["difficulty"], 0) + 1
        payload["meta"]["by_difficulty"] = by_diff
        payload["meta"]["glossed"] = sum(1 for v in verbs if v.get("gloss_es"))
        _OUT.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    # Resume-friendly: skip verbs already glossed (a prior run got them), so a
    # re-run after a cred expiry continues instead of redoing work.
    pending = [v for v in verbs if not v.get("gloss_es")]
    if len(pending) < len(verbs):
        print(f"Resuming: {len(verbs) - len(pending)} already glossed, "
              f"{len(pending)} to go", file=sys.stderr)

    updated = 0
    for start in range(0, len(pending), batch_size):
        batch = pending[start : start + batch_size]
        try:
            raw = _bedrock.bedrock_converse(
                _enrich_prompt(batch), model=model, max_tokens=4096, temperature=temperature,
            )
        except RuntimeError as exc:
            print(f"Bedrock call failed: {exc}", file=sys.stderr)
            if not dry_run:
                _checkpoint()  # keep everything enriched so far
                print(f"Checkpointed {updated} enriched verbs — re-run to resume.",
                      file=sys.stderr)
            return 1
        for item in _bedrock.extract_json_array(raw):
            if not isinstance(item, dict):
                continue
            match = by_id.get(item.get("id"))
            if match is None:
                continue
            diff = item.get("difficulty")
            if diff in _VALID_DIFFICULTIES:
                match["difficulty"] = diff
            gloss = item.get("gloss_es")
            if isinstance(gloss, str) and gloss.strip():
                match["gloss_es"] = gloss.strip()
            updated += 1
        if not dry_run:
            _checkpoint()  # per-batch durability
        print(f"  enriched {min(start + batch_size, len(pending))}/{len(pending)}",
              file=sys.stderr)

    by_diff = {}
    for v in verbs:
        by_diff[v["difficulty"]] = by_diff.get(v["difficulty"], 0) + 1
    if dry_run:
        print(f"(dry run) would update {updated} verbs with CEFR + ES gloss")
        print(f"(dry run) difficulty spread would be {by_diff}")
        return 0
    payload["meta"]["enriched"] = True
    _checkpoint()
    _OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Enriched {updated} verbs ({by_diff}) -> {_OUT.relative_to(_REPO)}")
    return 0


def _enrich_prompt(batch: list[dict[str, Any]]) -> str:
    """Build the Bedrock prompt for one enrichment batch."""
    items = [
        {"id": v["id"], "verb": v["verb"], "definitions": v["definitions"]}
        for v in batch
    ]
    return (
        "You are an English-as-a-foreign-language curriculum expert helping "
        "Spanish speakers. For each phrasal verb below, return a JSON array of "
        'objects with keys: "id" (unchanged), "difficulty" (one of "beginner", '
        '"intermediate", "advanced" by CEFR-style everyday usefulness for a '
        'learner), and "gloss_es" (a SHORT Spanish gloss of the meaning, 1-6 '
        "words, no article unless natural). Return ONLY the JSON array.\n\n"
        + json.dumps(items, ensure_ascii=False, indent=2)
    )


if __name__ == "__main__":
    raise SystemExit(main())
