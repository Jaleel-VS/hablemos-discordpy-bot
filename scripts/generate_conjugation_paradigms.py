#!/usr/bin/env python3
"""Precompute Spanish verb paradigms for the Activity conjugation game.

verbecc is the authoritative conjugation source, but it drags in
scikit-learn/scipy/numpy and *trains an ML model on first import* (~12s). That
is unacceptable on a request hot path and bloats the runtime image. So we run
verbecc **once, offline** (here or in the Docker build stage) and emit a compact
JSON the backend loads directly — the deployed image never needs the ML stack.

Output: ``activity/backend/app/games/data/conjugation_paradigms.json``

Shape::

    {
      "pronouns": ["yo", "tú", "él", "nosotros", "vosotros", "ellos"],
      "tenses":   {"presente": "Presente", "pretérito": "Pretérito", ...},
      "sets":     {"high-frequency": ["ser", ...], ...},
      "verbs": {
        "tener": {
          "english": "to have",
          "forms": {
            "presente": {"yo": "tengo", "tú": "tienes", ...},
            ...
          }
        },
        ...
      }
    }

The verb list and set membership are seeded from the existing native-Discord
cog (``cogs/conjugation_cog/verb_data.json``) so the two features agree on which
verbs are "high-frequency", "regular-ar", etc. Only the *forms* come from
verbecc (all tenses, correct irregulars) rather than the seed's hand-typed
3-tense tables.

Usage::

    pip install verbecc
    python scripts/generate_conjugation_paradigms.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# ── canonical teaching paradigm ──────────────────────────────────────────────
# The six pronoun slots every Spanish learner drills. verbecc also emits ella,
# usted, vos, ellas, ustedes; we collapse to one representative per slot so the
# game asks a clean 6-person paradigm.
PRONOUNS = ["yo", "tú", "él", "nosotros", "vosotros", "ellos"]

# Canonical tense key -> (verbecc Mood attr, verbecc Tense attr, display label).
# MVP ships the four core indicative tenses; add subjunctive/imperative here and
# they flow through the whole stack for free.
TENSES: dict[str, tuple[str, str, str]] = {
    "presente":   ("Indicativo", "Presente", "Presente"),
    "pretérito":  ("Indicativo", "PretéritoPerfectoSimple", "Pretérito"),
    "imperfecto": ("Indicativo", "PretéritoImperfecto", "Imperfecto"),
    "futuro":     ("Indicativo", "Futuro", "Futuro"),
}

# English glosses missing from the seed file, filled in here so every prompt can
# show a translation.
_EXTRA_GLOSSES = {
    "bailar": "to dance",
    "beber": "to drink",
    "caminar": "to walk",
    "cantar": "to sing",
    "cocinar": "to cook",
    "discutir": "to argue",
    "dividir": "to divide",
}

# verbecc 2.0.2 raises IndexError on a few otherwise-regular verbs (e.g.
# ``pasar``). For fully regular verbs we can supply the forms by hand rather
# than lose a common verb. Keyed by verb -> tense -> pronoun slot; merged in
# only when verbecc fails so the ML source stays authoritative for everything
# it can handle.
_MANUAL_FALLBACK: dict[str, dict[str, dict[str, str]]] = {
    "pasar": {
        "presente":   {"yo": "paso", "tú": "pasas", "él": "pasa",
                       "nosotros": "pasamos", "vosotros": "pasáis", "ellos": "pasan"},
        "pretérito":  {"yo": "pasé", "tú": "pasaste", "él": "pasó",
                       "nosotros": "pasamos", "vosotros": "pasasteis", "ellos": "pasaron"},
        "imperfecto": {"yo": "pasaba", "tú": "pasabas", "él": "pasaba",
                       "nosotros": "pasábamos", "vosotros": "pasabais", "ellos": "pasaban"},
        "futuro":     {"yo": "pasaré", "tú": "pasarás", "él": "pasará",
                       "nosotros": "pasaremos", "vosotros": "pasaréis", "ellos": "pasarán"},
    },
}

_REPO = Path(__file__).resolve().parent.parent
_SEED = _REPO / "cogs" / "conjugation_cog" / "verb_data.json"
_OUT = _REPO / "activity" / "backend" / "app" / "games" / "data" / "conjugation_paradigms.json"


def _strip_pronoun(pronoun: str, conjugated: str) -> str:
    """Turn verbecc's ``"yo tengo"`` into just ``"tengo"``.

    verbecc prefixes each conjugation with its pronoun. We want the bare verb
    form (that is what the player types), so drop the leading pronoun token.
    """
    prefix = pronoun + " "
    return conjugated[len(prefix):] if conjugated.startswith(prefix) else conjugated


def _build_forms(conjugate, verb: str) -> dict[str, dict[str, str]] | None:
    """All configured tenses for one verb, keyed by canonical pronoun slot.

    Returns ``None`` if verbecc can't conjugate the verb (so the caller skips it
    rather than emitting a half-empty entry).
    """
    from verbecc import Moods, Tenses  # local import: only needed at gen time

    try:
        full = conjugate(verb)
    except Exception as exc:
        fallback = _MANUAL_FALLBACK.get(verb)
        if fallback is not None:
            print(f"  ~ {verb!r}: verbecc failed ({exc}); using manual fallback", file=sys.stderr)
            return {key: fallback[key] for key in TENSES if key in fallback} or None
        print(f"  ! skipping {verb!r}: {exc}", file=sys.stderr)
        return None

    forms: dict[str, dict[str, str]] = {}
    for key, (mood_attr, tense_attr, _label) in TENSES.items():
        mood = full[getattr(Moods.es, mood_attr)]
        tense = mood[getattr(Tenses.es, tense_attr)]
        slot: dict[str, str] = {}
        for conj in tense:
            pron = conj.get_pronoun().value
            if pron not in PRONOUNS or pron in slot:
                continue  # keep one representative per canonical slot
            conjugations = conj.get_conjugations()
            if not conjugations:
                continue
            slot[pron] = _strip_pronoun(pron, conjugations[0])
        # Only keep the tense if we filled every pronoun slot cleanly.
        if all(p in slot for p in PRONOUNS):
            forms[key] = {p: slot[p] for p in PRONOUNS}
        else:
            missing = [p for p in PRONOUNS if p not in slot]
            print(f"  ! {verb!r} {key}: missing {missing}, dropping tense", file=sys.stderr)
    return forms or None


def main() -> int:
    if not _SEED.exists():
        print(f"seed file not found: {_SEED}", file=sys.stderr)
        return 1

    seed = json.loads(_SEED.read_text(encoding="utf-8"))
    categories = seed["categories"]
    glosses = seed.get("verbs", {})

    sets = {key: cat["verbs"] for key, cat in categories.items()}
    all_verbs = sorted({v for verbs in sets.values() for v in verbs})

    try:
        from verbecc import CompleteConjugator
        from verbecc import LangCodeISO639_1 as Lang
    except ImportError:
        print("verbecc is not installed. Run: pip install verbecc", file=sys.stderr)
        return 1

    print(f"Conjugating {len(all_verbs)} verbs with verbecc (trains model on first run)…")
    cc = CompleteConjugator(Lang.es)

    verbs_out: dict[str, dict] = {}
    for verb in all_verbs:
        forms = _build_forms(cc.conjugate, verb)
        if forms is None:
            continue
        english = glosses.get(verb, {}).get("english") or _EXTRA_GLOSSES.get(verb, "")
        verbs_out[verb] = {"english": english, "forms": forms}

    # Drop any verb from the sets that failed to conjugate, so the game never
    # references a verb without forms.
    clean_sets = {
        key: [v for v in verbs if v in verbs_out]
        for key, verbs in sets.items()
    }

    out = {
        "pronouns": PRONOUNS,
        "tenses": {key: spec[2] for key, spec in TENSES.items()},
        "sets": clean_sets,
        "verbs": verbs_out,
    }

    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(
        json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    missing_gloss = [v for v, d in verbs_out.items() if not d["english"]]
    print(f"Wrote {len(verbs_out)} verbs × {len(TENSES)} tenses -> {_OUT.relative_to(_REPO)}")
    if missing_gloss:
        print(f"  (no english gloss for: {missing_gloss})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
