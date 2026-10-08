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
      "sets":     {"high-frequency": ["ser", ...], "stem-changers": [...], ...},
      "verbs": {
        "tener": {
          "english": "to have",
          "forms": {
            "presente": {"yo": "tengo", "tú": "tienes", ...},
            ...
          },
          "classes": ["go-verb", "stem-change-e-ie", "strong-preterite", ...],
          "notes": {"presente": "Irregular yo: tengo (-go verb). ...", ...}
        },
        ...
      }
    }

The verb list and set membership are seeded from
``activity/backend/app/games/data/conjugation_seed.json`` so the verb sets stay
stable ("high-frequency", "regular-ar", etc.). Only the *forms* come from
verbecc (all tenses, correct irregulars) rather than the seed's hand-typed
3-tense tables.

Usage::

    uv run --with verbecc python scripts/generate_conjugation_paradigms.py

The generator **fails loudly** (exit 1, no write) if any seed verb or any
configured tense would be dropped from the output — a silent shrink would
change the deterministic daily sequence for everyone and quietly shrink
freeplay pools. Pass ``--allow-drops`` to regenerate anyway (writing the
smaller JSON) after you've reviewed and accepted the drops.
"""
from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path

# ── canonical teaching paradigm ──────────────────────────────────────────────
# The six pronoun slots every Spanish learner drills. verbecc also emits ella,
# usted, vos, ellas, ustedes; we collapse to one representative per slot so the
# game asks a clean 6-person paradigm.
PRONOUNS = ["yo", "tú", "él", "nosotros", "vosotros", "ellos"]

# Canonical tense key -> (verbecc Mood attr, verbecc Tense attr, display label).
# Daily mode pins ["presente","pretérito","imperfecto","futuro"] explicitly;
# adding tenses here does not affect the daily sequence.
TENSES: dict[str, tuple[str, str, str]] = {
    "presente":    ("Indicativo",   "Presente",               "Presente"),
    "pretérito":   ("Indicativo",   "PretéritoPerfectoSimple", "Pretérito"),
    "imperfecto":  ("Indicativo",   "PretéritoImperfecto",     "Imperfecto"),
    "futuro":      ("Indicativo",   "Futuro",                  "Futuro"),
    "condicional": ("Condicional",  "Presente",                "Condicional"),
    "subjuntivo":  ("Subjuntivo",   "Presente",                "Subjuntivo"),
}

# English glosses missing from the seed file, filled in here so every prompt can
# show a translation.
_EXTRA_GLOSSES: dict[str, str] = {
    "bailar":     "to dance",
    "beber":      "to drink",
    "caminar":    "to walk",
    "cantar":     "to sing",
    "cocinar":    "to cook",
    "discutir":   "to argue",
    "dividir":    "to divide",
}

# verbecc 2.0.2 raises IndexError on a few otherwise-regular verbs (e.g.
# ``pasar``). For fully regular verbs we can supply the forms by hand rather
# than lose a common verb. Keyed by verb -> tense -> pronoun slot; merged in
# only when verbecc fails so the ML source stays authoritative for everything
# it can handle.
_MANUAL_FALLBACK: dict[str, dict[str, dict[str, str]]] = {
    "pasar": {
        "presente":    {"yo": "paso",     "tú": "pasas",     "él": "pasa",
                        "nosotros": "pasamos",  "vosotros": "pasáis",  "ellos": "pasan"},
        "pretérito":   {"yo": "pasé",     "tú": "pasaste",   "él": "pasó",
                        "nosotros": "pasamos",  "vosotros": "pasasteis", "ellos": "pasaron"},
        "imperfecto":  {"yo": "pasaba",   "tú": "pasabas",   "él": "pasaba",
                        "nosotros": "pasábamos", "vosotros": "pasabais", "ellos": "pasaban"},
        "futuro":      {"yo": "pasaré",   "tú": "pasarás",   "él": "pasará",
                        "nosotros": "pasaremos", "vosotros": "pasaréis", "ellos": "pasarán"},
        "condicional": {"yo": "pasaría",  "tú": "pasarías",  "él": "pasaría",
                        "nosotros": "pasaríamos", "vosotros": "pasaríais", "ellos": "pasarían"},
        "subjuntivo":  {"yo": "pase",     "tú": "pases",     "él": "pase",
                        "nosotros": "pasemos",  "vosotros": "paséis",  "ellos": "pasen"},
    },
    "reír": {
        "presente":    {"yo": "río",      "tú": "ríes",      "él": "ríe",
                        "nosotros": "reímos",   "vosotros": "reís",    "ellos": "ríen"},
        "pretérito":   {"yo": "reí",      "tú": "reíste",    "él": "rió",
                        "nosotros": "reímos",   "vosotros": "reísteis", "ellos": "rieron"},
        "imperfecto":  {"yo": "reía",     "tú": "reías",     "él": "reía",
                        "nosotros": "reíamos",  "vosotros": "reíais",  "ellos": "reían"},
        "futuro":      {"yo": "reiré",    "tú": "reirás",    "él": "reirá",
                        "nosotros": "reiremos", "vosotros": "reiréis", "ellos": "reirán"},
        "condicional": {"yo": "reiría",   "tú": "reirías",   "él": "reiría",
                        "nosotros": "reiríamos", "vosotros": "reiríais", "ellos": "reirían"},
        "subjuntivo":  {"yo": "ría",      "tú": "rías",      "él": "ría",
                        "nosotros": "riamos",   "vosotros": "riáis",   "ellos": "rían"},
    },
    "sonreír": {
        "presente":    {"yo": "sonrío",   "tú": "sonríes",   "él": "sonríe",
                        "nosotros": "sonreímos", "vosotros": "sonreís", "ellos": "sonríen"},
        "pretérito":   {"yo": "sonreí",   "tú": "sonreíste", "él": "sonrió",
                        "nosotros": "sonreímos", "vosotros": "sonreísteis", "ellos": "sonrieron"},
        "imperfecto":  {"yo": "sonreía",  "tú": "sonreías",  "él": "sonreía",
                        "nosotros": "sonreíamos", "vosotros": "sonreíais", "ellos": "sonreían"},
        "futuro":      {"yo": "sonreiré", "tú": "sonreirás", "él": "sonreirá",
                        "nosotros": "sonreiremos", "vosotros": "sonreiréis", "ellos": "sonreirán"},
        "condicional": {"yo": "sonreiría", "tú": "sonreirías", "él": "sonreiría",
                        "nosotros": "sonreiríamos", "vosotros": "sonreiríais", "ellos": "sonreirían"},
        "subjuntivo":  {"yo": "sonría",   "tú": "sonrías",   "él": "sonría",
                        "nosotros": "sonriamos", "vosotros": "sonriáis", "ellos": "sonrían"},
    },
    "oír": {
        "presente":    {"yo": "oigo",     "tú": "oyes",      "él": "oye",
                        "nosotros": "oímos",    "vosotros": "oís",     "ellos": "oyen"},
        "pretérito":   {"yo": "oí",       "tú": "oíste",     "él": "oyó",
                        "nosotros": "oímos",    "vosotros": "oísteis", "ellos": "oyeron"},
        "imperfecto":  {"yo": "oía",      "tú": "oías",      "él": "oía",
                        "nosotros": "oíamos",   "vosotros": "oíais",   "ellos": "oían"},
        "futuro":      {"yo": "oiré",     "tú": "oirás",     "él": "oirá",
                        "nosotros": "oiremos",  "vosotros": "oiréis",  "ellos": "oirán"},
        "condicional": {"yo": "oiría",    "tú": "oirías",    "él": "oiría",
                        "nosotros": "oiríamos", "vosotros": "oiríais", "ellos": "oirían"},
        "subjuntivo":  {"yo": "oiga",     "tú": "oigas",     "él": "oiga",
                        "nosotros": "oigamos",  "vosotros": "oigáis",  "ellos": "oigan"},
    },
    "haber": {
        "presente":    {"yo": "he",       "tú": "has",       "él": "ha",
                        "nosotros": "hemos",    "vosotros": "habéis",  "ellos": "han"},
        "pretérito":   {"yo": "hube",     "tú": "hubiste",   "él": "hubo",
                        "nosotros": "hubimos",  "vosotros": "hubisteis", "ellos": "hubieron"},
        "imperfecto":  {"yo": "había",    "tú": "habías",    "él": "había",
                        "nosotros": "habíamos", "vosotros": "habíais", "ellos": "habían"},
        "futuro":      {"yo": "habré",    "tú": "habrás",    "él": "habrá",
                        "nosotros": "habremos", "vosotros": "habréis", "ellos": "habrán"},
        "condicional": {"yo": "habría",   "tú": "habrías",   "él": "habría",
                        "nosotros": "habríamos", "vosotros": "habríais", "ellos": "habrían"},
        "subjuntivo":  {"yo": "haya",     "tú": "hayas",     "él": "haya",
                        "nosotros": "hayamos",  "vosotros": "hayáis",  "ellos": "hayan"},
    },
}

_REPO = Path(__file__).resolve().parent.parent
_SEED = _REPO / "activity" / "backend" / "app" / "games" / "data" / "conjugation_seed.json"
_OUT = _REPO / "activity" / "backend" / "app" / "games" / "data" / "conjugation_paradigms.json"

# Verbs that are fully irregular and should not be classified by rule-heuristics.
_FULLY_IRREGULAR_VERBS = frozenset({"ser", "ir", "estar", "dar", "ver", "haber"})


# ── regular paradigm synthesiser ─────────────────────────────────────────────

def _regular_paradigm(verb: str, tense: str) -> dict[str, str] | None:
    """Compute the *expected* fully-regular forms for *verb* in *tense*.

    Returns ``None`` if the verb ending or tense is unrecognised.  The caller
    compares these forms to the verbecc-derived actuals to detect irregularities.
    """
    if verb.endswith("ar"):
        conj = "ar"
        stem = verb[:-2]
    elif verb.endswith("er"):
        conj = "er"
        stem = verb[:-2]
    elif verb.endswith(("ir", "ír")):
        # reír / oír / freír carry an orthographic accent on the infinitive;
        # the regular stem is still the letters before -ir.
        conj = "ir"
        stem = verb[:-2]
    else:
        return None

    if tense == "presente":
        if conj == "ar":
            endings = ["o", "as", "a", "amos", "áis", "an"]
        elif conj == "er":
            endings = ["o", "es", "e", "emos", "éis", "en"]
        else:  # ir
            endings = ["o", "es", "e", "imos", "ís", "en"]
    elif tense == "pretérito":
        if conj == "ar":
            endings = ["é", "aste", "ó", "amos", "asteis", "aron"]
        else:
            endings = ["í", "iste", "ió", "imos", "isteis", "ieron"]
    elif tense == "imperfecto":
        if conj == "ar":
            endings = ["aba", "abas", "aba", "ábamos", "abais", "aban"]
        else:
            endings = ["ía", "ías", "ía", "íamos", "íais", "ían"]
    elif tense == "futuro":
        stem = _strip_accents(verb)  # infinitive; reír → reiré drops the accent
        endings = ["é", "ás", "á", "emos", "éis", "án"]
    elif tense == "condicional":
        stem = _strip_accents(verb)
        endings = ["ía", "ías", "ía", "íamos", "íais", "ían"]
    elif tense == "subjuntivo":
        if conj == "ar":
            endings = ["e", "es", "e", "emos", "éis", "en"]
        else:
            endings = ["a", "as", "a", "amos", "áis", "an"]
    else:
        return None

    return {p: stem + e for p, e in zip(PRONOUNS, endings, strict=True)}


# ── irregularity classifier ───────────────────────────────────────────────────

def _classify_verb(
    verb: str, forms: dict[str, dict[str, str]]
) -> tuple[list[str], dict[str, str]]:
    """Derive `classes` and learner-facing `notes` by comparing *forms* to the
    regular paradigm synthesised for *verb*.

    Returns a tuple of:
    - ``classes``: sorted list of class strings (at least ``["regular"]``).
    - ``notes``: dict of ``{tense_key: one-line note}`` for irregular tenses only.
    """
    classes: set[str] = set()

    # ── fully-irregular shortcut ─────────────────────────────────────────────
    if verb in _FULLY_IRREGULAR_VERBS:
        classes.add("fully-irregular")
        notes = _notes_for_fully_irregular(verb, forms)
        return sorted(classes), notes

    pres = forms.get("presente", {})
    pret = forms.get("pretérito", {})
    reg_pres = _regular_paradigm(verb, "presente") or {}
    reg_pret = _regular_paradigm(verb, "pretérito") or {}
    reg_fut  = _regular_paradigm(verb, "futuro") or {}
    reg_cond = _regular_paradigm(verb, "condicional") or {}
    reg_subj = _regular_paradigm(verb, "subjuntivo") or {}

    yo_pres  = pres.get("yo", "")

    # ── go-verb ──────────────────────────────────────────────────────────────
    # yo presente ends in -go where the regular form doesn't
    if yo_pres.endswith("go") and not reg_pres.get("yo", "").endswith("go"):
        classes.add("go-verb")

    # ── zco-verb ─────────────────────────────────────────────────────────────
    if yo_pres.endswith("zco"):
        classes.add("zco-verb")

    # ── stem-change detection in the "boot" forms ────────────────────────────
    # Boot forms: yo, tú, él, ellos change; nosotros/vosotros stay regular.
    non_yo_boot_changed = any(pres.get(p) != reg_pres.get(p) for p in ["tú", "él", "ellos"])
    nos_match = (pres.get("nosotros") == reg_pres.get("nosotros")
                 and pres.get("vosotros") == reg_pres.get("vosotros"))

    if verb.endswith("eír"):
        # reír / freír / sonreír: e→i in the boot forms (río, ríes) with a
        # written accent on the i; nosotros keeps the infinitive's accent
        # (reímos), so the generic nosotros check below would never match.
        classes.add("stem-change-e-i")
    elif verb.endswith("uir") and not verb.endswith("guir") and pres.get("yo", "").endswith("yo"):
        # construir / huir / incluir: a y is inserted before the ending in the
        # boot forms (construyo, construyes). Handled by the y-insertion
        # check below — don't also call it a vowel stem change.
        pass
    elif non_yo_boot_changed and nos_match and reg_pres:
        # Use tú to determine the change type (yo may be a go-verb form).
        tu_actual = pres.get("tú", "")
        tu_reg    = reg_pres.get("tú", "")
        # Strip the expected tú-present ending to expose the stem.
        tu_end = "as" if verb.endswith("ar") else "es"
        tu_actual_stem = tu_actual[:-len(tu_end)] if tu_actual.endswith(tu_end) else tu_actual
        tu_reg_stem    = tu_reg[:-len(tu_end)]    if tu_reg.endswith(tu_end)    else tu_reg

        if _strip_accents(tu_actual_stem) == tu_reg_stem:
            # actúas, reúnes, prohíbes: same letters, a written accent
            # breaks the diphthong in the boot forms. Not a vowel change.
            classes.add("accent-shift")
        elif "ie" in tu_actual_stem and "ie" not in tu_reg_stem:
            classes.add("stem-change-e-ie")
        elif "ue" in tu_actual_stem and "ue" not in tu_reg_stem:
            if verb.endswith("ugar"):
                classes.add("stem-change-u-ue")
            else:
                classes.add("stem-change-o-ue")
        elif tu_actual_stem != tu_reg_stem:
            classes.add("stem-change-e-i")

    # ── -ger/-gir g→j, consonant+-cer c→z in yo presente (cojo, venzo) ──────
    # Predictable spelling rules (keep the consonant's sound before -o), not a
    # stem change; they carry into the whole present subjunctive.
    if (
        (verb.endswith(("ger", "gir")) and yo_pres.endswith("jo"))
        or (verb.endswith("cer") and yo_pres.endswith("zo"))
    ) and reg_pres.get("yo", "").endswith(("go", "co")):
        classes.add("spelling-change-ger-gir")

    # ── strong preterite ─────────────────────────────────────────────────────
    # yo pretérito ends in an unaccented 'e' (tuve, puse, hice…).
    yo_pret = pret.get("yo", "")
    if yo_pret and yo_pret[-1] == "e" and yo_pret[-1] != "é":
        classes.add("strong-preterite")

    # ── spelling-change -car/-gar/-zar ───────────────────────────────────────
    yo_pret_val = pret.get("yo", "")
    if (verb.endswith("car") and yo_pret_val.endswith("qué")) or (verb.endswith("gar") and yo_pret_val.endswith("gué")) or (verb.endswith("zar") and yo_pret_val.endswith("cé")):
        classes.add("spelling-change-car-gar-zar")

    # ── y-insertion ──────────────────────────────────────────────────────────
    # él pretérito contains 'y' where regular doesn't (leyó, construyó, oyó…)
    # OR yo presente contains 'y' (construyo, huyo…).
    el_pret  = pret.get("él", "")
    reg_el_pret = reg_pret.get("él", "")
    yo_pres_val = pres.get("yo", "")
    reg_yo_pres = reg_pres.get("yo", "")
    if (("y" in el_pret and el_pret != reg_el_pret)
            or ("y" in yo_pres_val and yo_pres_val != reg_yo_pres
                and not classes.intersection({"go-verb", "zco-verb"}))):
        classes.add("y-insertion")

    # ── irregular future ─────────────────────────────────────────────────────
    # Compare accent-stripped so freír → freiré (regular stem, accent dropped
    # by the orthography) isn't mistaken for a tendr-/podr- style stem.
    yo_fut = forms.get("futuro", {}).get("yo", "")
    if yo_fut and _strip_accents(yo_fut) != _strip_accents(verb + "é"):
        classes.add("irregular-future")


    if not classes:
        classes.add("regular")

    notes = _build_notes(verb, forms, classes, reg_pres, reg_pret, reg_fut, reg_cond, reg_subj)
    return sorted(classes), notes


def _notes_for_fully_irregular(
    verb: str, forms: dict[str, dict[str, str]]
) -> dict[str, str]:
    """Concise per-tense notes for the six fully-irregular verbs.

    Only tenses that actually deviate from the regular paradigm get a note —
    ``ser`` is regular in futuro/condicional (seré, sería), so stamping
    "memorise all forms" there would teach the wrong lesson.
    """
    notes: dict[str, str] = {}
    for tense, slot in forms.items():
        regular = _regular_paradigm(verb, tense)
        if regular is not None and all(slot.get(p) == regular.get(p) for p in PRONOUNS):
            continue
        yo = slot.get("yo", "")
        tu = slot.get("tú", "")
        notes[tense] = f"Fully irregular: yo {yo}, tú {tu}. Memorise all forms."[:120]
    return notes


def _build_notes(
    verb: str,
    forms: dict[str, dict[str, str]],
    classes: set[str],
    reg_pres: dict[str, str],
    reg_pret: dict[str, str],
    reg_fut:  dict[str, str],
    reg_cond: dict[str, str],
    reg_subj: dict[str, str],
) -> dict[str, str]:
    """Generate learner-facing notes (≤120 chars each) for irregular tenses."""
    notes: dict[str, str] = {}

    sc_class = next((c for c in classes if c.startswith("stem-change")), None)
    sc_desc = {
        "stem-change-e-ie": "e→ie",
        "stem-change-o-ue": "o→ue",
        "stem-change-e-i":  "e→i",
        "stem-change-u-ue": "u→ue",
    }.get(sc_class or "", "")

    pres = forms.get("presente", {})
    pret = forms.get("pretérito", {})
    fut  = forms.get("futuro", {})
    cond = forms.get("condicional", {})
    subj = forms.get("subjuntivo", {})

    # ── presente ─────────────────────────────────────────────────────────────
    is_pres_irregular = any(pres.get(p) != reg_pres.get(p) for p in PRONOUNS)
    if is_pres_irregular:
        yo_f = pres.get("yo", "")
        if "go-verb" in classes:
            note = f"Irregular yo: {yo_f} (-go verb)."
            if sc_desc:
                tu_f = pres.get("tú", "")
                note += f" Stem {sc_desc} in tú/él/ellos (e.g. {tu_f})."
        elif "zco-verb" in classes:
            note = f"Irregular yo: {yo_f} (-zco verb). Other present forms regular."
        elif "spelling-change-ger-gir" in classes:
            swap = "c→z" if verb.endswith("cer") else "g→j"
            note = f"Spelling only: {swap} in yo ({yo_f}) to keep the sound. Rest regular."
        elif "accent-shift" in classes:
            tu_f  = pres.get("tú", "")
            nos_f = pres.get("nosotros", "")
            note = f"Written accent in yo/tú/él/ellos ({yo_f}, {tu_f}); nosotros {nos_f}."
        elif sc_class:
            tu_f  = pres.get("tú", "")
            nos_f = pres.get("nosotros", "")
            note = f"Stem {sc_desc} in yo/tú/él/ellos (e.g. {tu_f}); nosotros {nos_f}."
        elif "y-insertion" in classes:
            tu_f = pres.get("tú", "")
            note = f"y replaces i before a vowel: yo {yo_f}, tú {tu_f}."
        else:
            note = f"Irregular present: yo {yo_f}."
        notes["presente"] = note[:120]

    # ── pretérito ─────────────────────────────────────────────────────────────
    is_pret_irregular = any(pret.get(p) != reg_pret.get(p) for p in PRONOUNS)
    if is_pret_irregular:
        yo_f = pret.get("yo", "")
        tu_f = pret.get("tú", "")
        if "strong-preterite" in classes:
            note = f"Strong preterite: {yo_f}, {tu_f}. No accents on endings."
        elif "spelling-change-car-gar-zar" in classes:
            note = f"Spelling change yo only: {yo_f}. Other persons regular."
        elif "y-insertion" in classes:
            el_f    = pret.get("él", "")
            ellos_f = pret.get("ellos", "")
            note = f"y-insertion in 3rd persons: {el_f}, {ellos_f}."
        elif sc_class and verb.endswith(("ir", "ír")):
            el_f    = pret.get("él", "")
            ellos_f = pret.get("ellos", "")
            shift = "o→u" if sc_class == "stem-change-o-ue" else "e→i"
            note = f"-ir stem changer: {shift} in él/ellos only ({el_f}, {ellos_f}). Rest regular."
        else:
            note = f"Irregular preterite: {yo_f}, {tu_f}."
        notes["pretérito"] = note[:120]

    # ── imperfecto ────────────────────────────────────────────────────────────
    reg_imp = _regular_paradigm(verb, "imperfecto") or {}
    imp = forms.get("imperfecto", {})
    if any(imp.get(p) != reg_imp.get(p) for p in PRONOUNS):
        yo_f = imp.get("yo", "")
        notes["imperfecto"] = f"Irregular imperfect: yo {yo_f}. Memorise all forms."[:120]

    # ── futuro ────────────────────────────────────────────────────────────────
    is_fut_irregular = any(fut.get(p) != reg_fut.get(p) for p in PRONOUNS)
    if is_fut_irregular:
        yo_f = fut.get("yo", "")
        tu_f = fut.get("tú", "")
        stem = yo_f[:-1] if yo_f.endswith("é") else yo_f
        notes["futuro"] = f"Irregular future stem {stem}-: {yo_f}, {tu_f}."[:120]

    # ── condicional ───────────────────────────────────────────────────────────
    is_cond_irregular = any(cond.get(p) != reg_cond.get(p) for p in PRONOUNS)
    if is_cond_irregular:
        yo_f = cond.get("yo", "")
        tu_f = cond.get("tú", "")
        stem = yo_f[:-2] if yo_f.endswith("ía") else yo_f
        notes["condicional"] = f"Irregular conditional stem {stem}-: {yo_f}, {tu_f}."[:120]

    # ── subjuntivo ────────────────────────────────────────────────────────────
    is_subj_irregular = any(subj.get(p) != reg_subj.get(p) for p in PRONOUNS)
    if is_subj_irregular:
        yo_f = subj.get("yo", "")
        if "go-verb" in classes:
            note = f"Subjunctive built from yo present stem (-go → -ga): {yo_f}."
        elif "zco-verb" in classes:
            note = f"Subjunctive built from yo present stem (-zco → -zca): {yo_f}."
        elif "spelling-change-ger-gir" in classes:
            swap = "c→z" if verb.endswith("cer") else "g→j"
            note = f"{swap} throughout the subjunctive (from yo {pres.get('yo', '')}): {yo_f}."
        elif "y-insertion" in classes and verb.endswith("uir"):
            note = f"Keeps the y from the present throughout: yo {yo_f}, nosotros {subj.get('nosotros', '')}."
        elif "accent-shift" in classes:
            note = f"Same accent pattern as the present: yo {yo_f}, nosotros {subj.get('nosotros', '')}."
        elif sc_class and verb.endswith("ir"):
            note = f"-ir stem changer also shifts in subjunctive: yo {yo_f}."
        elif sc_class:
            note = f"Stem {sc_desc} in the boot forms, like the present: yo {yo_f}."
        elif "spelling-change-car-gar-zar" in classes:
            note = f"Spelling from infinitive applied throughout: yo {yo_f}."
        else:
            note = f"Irregular subjunctive: yo {yo_f}."
        notes["subjuntivo"] = note[:120]

    return notes


# ── verbecc extraction ────────────────────────────────────────────────────────

def _strip_pronoun(pronoun: str, conjugated: str) -> str:
    """Turn verbecc's ``"yo tengo"`` into just ``"tengo"``.

    verbecc prefixes each conjugation with its pronoun. We want the bare verb
    form (that is what the player types), so drop the leading pronoun token.
    """
    prefix = pronoun + " "
    return conjugated[len(prefix):] if conjugated.startswith(prefix) else conjugated


def _strip_accents(text: str) -> str:
    """``actúas`` → ``actuas`` (ñ is preserved; it's a letter, not an accent)."""
    decomposed = unicodedata.normalize("NFD", text.replace("ñ", "\x00"))
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return stripped.replace("\x00", "ñ")


def _build_forms(conjugate, verb: str) -> dict[str, dict[str, str]] | None:
    """All configured tenses for one verb, keyed by canonical pronoun slot.

    Returns ``None`` if verbecc can't conjugate the verb (so the caller skips it
    rather than emitting a half-empty entry).
    """
    from verbecc import Moods, Tenses  # local import: only needed at gen time

    mood_attrs = {
        "Indicativo":  Moods.es.Indicativo,
        "Condicional": Moods.es.Condicional,
        "Subjuntivo":  Moods.es.Subjuntivo,
    }
    tense_attrs = {
        "Presente":               Tenses.es.Presente,
        "PretéritoPerfectoSimple": Tenses.es.PretéritoPerfectoSimple,
        "PretéritoImperfecto":    Tenses.es.PretéritoImperfecto,
        "Futuro":                 Tenses.es.Futuro,
    }

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
        tense_obj = full[mood_attrs[mood_attr]][tense_attrs[tense_attr]]
        slot: dict[str, str] = {}
        for conj in tense_obj:
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
            # Try manual fallback for this tense.
            if verb in _MANUAL_FALLBACK and key in _MANUAL_FALLBACK[verb]:
                forms[key] = _MANUAL_FALLBACK[verb][key]
            else:
                missing = [p for p in PRONOUNS if p not in slot]
                print(f"  ! {verb!r} {key}: missing {missing}, dropping tense", file=sys.stderr)
    return forms or None


def _report_drops(all_verbs: list[str], verbs_out: dict[str, dict]) -> list[str]:
    """Human-readable list of every seed verb or configured tense that got
    dropped from the output. Empty list == the full seed grid survived."""
    drops: list[str] = []
    dropped_verbs = [v for v in all_verbs if v not in verbs_out]
    if dropped_verbs:
        drops.append(f"{len(dropped_verbs)} verb(s) dropped entirely: {dropped_verbs}")
    for key in TENSES:
        missing_from = [v for v, d in verbs_out.items() if key not in d["forms"]]
        if len(missing_from) == len(verbs_out):
            drops.append(f"tense {key!r} present in NO verb")
        elif missing_from:
            drops.append(f"tense {key!r} missing from {len(missing_from)} verb(s): {missing_from}")
    return drops


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-drops",
        action="store_true",
        help="write the JSON even if seed verbs/tenses were dropped",
    )
    args = parser.parse_args()

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
        print(
            "verbecc is not installed. "
            "Run: uv run --with verbecc python scripts/generate_conjugation_paradigms.py",
            file=sys.stderr,
        )
        return 1

    print(f"Conjugating {len(all_verbs)} verbs with verbecc (trains model on first run)…")
    cc = CompleteConjugator(Lang.es)

    verbs_out: dict[str, dict] = {}
    for verb in all_verbs:
        forms = _build_forms(cc.conjugate, verb)
        if forms is None:
            continue
        english = glosses.get(verb, {}).get("english") or _EXTRA_GLOSSES.get(verb, "")
        classes, notes = _classify_verb(verb, forms)
        verbs_out[verb] = {
            "classes": classes,
            "english": english,
            "forms": forms,
            "notes": notes,
        }

    # Drop any verb from the sets that failed to conjugate, so the game never
    # references a verb without forms.
    clean_sets = {
        key: [v for v in verbs if v in verbs_out]
        for key, verbs in sets.items()
    }

    # ── derived sets ──────────────────────────────────────────────────────────
    derived: dict[str, list[str]] = {
        "stem-changers": [
            v for v, d in verbs_out.items()
            if any(c.startswith("stem-change") for c in d["classes"])
        ],
        "go-verbs": [
            v for v, d in verbs_out.items()
            if any(c in ("go-verb", "zco-verb") for c in d["classes"])
        ],
        "strong-preterite": [
            v for v, d in verbs_out.items()
            if "strong-preterite" in d["classes"]
        ],
        "spelling-changers": [
            v for v, d in verbs_out.items()
            if any(
                c in ("spelling-change-car-gar-zar", "spelling-change-ger-gir", "y-insertion")
                for c in d["classes"]
            )
        ],
        "accent-shifters": [
            v for v, d in verbs_out.items()
            if "accent-shift" in d["classes"]
        ],
    }
    for dkey, dverbs in derived.items():
        if len(dverbs) >= 4:
            clean_sets[dkey] = sorted(dverbs)

    # Drift guard: refuse to silently ship a smaller game. A dropped verb/tense
    # shifts the deterministic daily sequence and shrinks freeplay pools, so it
    # must be an explicit, reviewed decision (--allow-drops).
    drops = _report_drops(all_verbs, verbs_out)
    if drops:
        print("\nDROPPED from the seed grid:", file=sys.stderr)
        for line in drops:
            print(f"  - {line}", file=sys.stderr)
        if not args.allow_drops:
            print(
                "\nRefusing to write (would change the daily sequence / shrink "
                "pools). Re-run with --allow-drops once you've accepted these.",
                file=sys.stderr,
            )
            return 1
        print("\n--allow-drops set: writing the smaller paradigm anyway.", file=sys.stderr)

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

    # Print classes distribution summary.
    from collections import Counter
    dist: Counter[str] = Counter()
    for d in verbs_out.values():
        for c in d["classes"]:
            dist[c] += 1
    print("Classes distribution:")
    for cls, cnt in dist.most_common():
        print(f"  {cls}: {cnt}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
