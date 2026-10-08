"""Integrity checks on the committed conjugation paradigm JSON.

The generator (scripts/generate_conjugation_paradigms.py) can silently drop
verbs/tenses on a verbecc change; it now refuses to write on drift, but this
guards the *committed* artifact directly — if the JSON ever drifts from the
seed verb list or loses a paradigm cell, this fails in CI, not in production
(where it would silently reshape the daily sequence and shrink freeplay pools).
No verbecc needed — reads the shipped JSON and the seed file.
"""
import json
from pathlib import Path

from app.games.conjugation import data as d

_REPO = Path(__file__).resolve().parents[3]
_SEED = _REPO / "activity" / "backend" / "app" / "games" / "data" / "conjugation_seed.json"

# Regression pin: the exact 30-verb high-frequency list that the daily sequence
# depends on. Order matters — changing this list shifts every day's sequence.
_HIGH_FREQUENCY_FROZEN = [
    "ser", "estar", "tener", "hacer", "poder", "decir", "ir", "ver", "dar",
    "saber", "querer", "llegar", "pasar", "deber", "poner", "parecer", "quedar",
    "creer", "hablar", "llevar", "dejar", "seguir", "encontrar", "llamar",
    "venir", "pensar", "salir", "volver", "tomar", "conocer",
]


def _seed_verbs() -> set[str]:
    seed = json.loads(_SEED.read_text(encoding="utf-8"))
    return {v for cat in seed["categories"].values() for v in cat["verbs"]}


def test_every_seed_verb_is_present():
    missing = _seed_verbs() - set(d.VERBS)
    assert not missing, f"seed verbs missing from paradigm JSON: {sorted(missing)}"


def test_full_paradigm_grid_for_every_verb():
    """Every verb must carry all 6 configured tenses × all 6 canonical pronouns."""
    incomplete: list[str] = []
    for verb, entry in d.VERBS.items():
        forms = entry["forms"]
        for tense in d.TENSES:
            slot = forms.get(tense)
            if slot is None or any(p not in slot for p in d.PRONOUNS):
                incomplete.append(f"{verb}/{tense}")
    assert not incomplete, f"incomplete paradigm cells: {incomplete}"


def test_all_six_tenses_present():
    """All 6 tenses (including condicional, subjuntivo) must be in every verb."""
    expected_tenses = {"presente", "pretérito", "imperfecto", "futuro", "condicional", "subjuntivo"}
    actual_tenses = set(d.TENSES.keys())
    assert expected_tenses == actual_tenses, (
        f"expected tenses {expected_tenses}, got {actual_tenses}"
    )


def test_every_set_member_resolves_to_a_real_verb():
    dangling = {
        f"{key}:{v}"
        for key, verbs in d.SETS.items()
        for v in verbs
        if v not in d.VERBS
    }
    assert not dangling, f"set members without forms: {sorted(dangling)}"


def test_no_pronoun_prefix_leaked_into_forms():
    # _strip_pronoun should have removed verbecc's "yo hablo" prefix; a leaked
    # prefix would make the expected answer un-typable.
    leaked = [
        f"{verb}/{tense}/{pron}"
        for verb, entry in d.VERBS.items()
        for tense, slot in entry["forms"].items()
        for pron, form in slot.items()
        if form.startswith(pron + " ")
    ]
    assert not leaked, f"forms with leaked pronoun prefix: {leaked}"


def test_every_verb_has_classes():
    """Every verb entry must have a non-empty 'classes' list."""
    missing = [v for v, entry in d.VERBS.items() if not entry.get("classes")]
    assert not missing, f"verbs missing 'classes': {missing}"


def test_classes_are_valid_strings():
    """All class values must be known strings from the defined vocabulary."""
    valid_classes = {
        "regular",
        "stem-change-e-ie",
        "stem-change-o-ue",
        "stem-change-e-i",
        "stem-change-u-ue",
        "go-verb",
        "zco-verb",
        "strong-preterite",
        "spelling-change-car-gar-zar",
        "y-insertion",
        "irregular-future",
        "fully-irregular",
        "accent-shift",
        "spelling-change-ger-gir",
    }
    unknown: list[str] = []
    for verb, entry in d.VERBS.items():
        for cls in entry.get("classes", []):
            if cls not in valid_classes:
                unknown.append(f"{verb}: {cls!r}")
    assert not unknown, f"unknown class values: {unknown}"


def test_every_verb_has_notes_dict():
    """Every verb entry must have a 'notes' dict (may be empty for regular verbs)."""
    missing = [v for v, entry in d.VERBS.items() if "notes" not in entry]
    assert not missing, f"verbs missing 'notes' key: {missing}"


def test_notes_keys_are_subset_of_tenses():
    """Note keys must be tense keys defined in TENSES."""
    valid = set(d.TENSES.keys())
    bad: list[str] = []
    for verb, entry in d.VERBS.items():
        for key in entry.get("notes", {}):
            if key not in valid:
                bad.append(f"{verb}: {key!r}")
    assert not bad, f"notes with invalid tense keys: {bad}"


def test_regular_verbs_have_regular_class():
    """Verbs whose class list contains only 'regular' must have no notes."""
    issues: list[str] = []
    for verb, entry in d.VERBS.items():
        classes = entry.get("classes", [])
        notes = entry.get("notes", {})
        if classes == ["regular"] and notes:
            issues.append(f"{verb}: classes=['regular'] but has notes {list(notes.keys())}")
    assert not issues, f"regular verbs with unexpected notes: {issues}"


def test_notes_are_short():
    """All notes must be ≤120 characters (learner-facing; no walls of text)."""
    too_long: list[str] = []
    for verb, entry in d.VERBS.items():
        for tense, note in entry.get("notes", {}).items():
            if len(note) > 120:
                too_long.append(f"{verb}/{tense} ({len(note)} chars)")
    assert not too_long, f"notes exceeding 120 chars: {too_long}"


def test_derived_sets_exist_with_min_members():
    """stem-changers, go-verbs, strong-preterite, spelling-changers must each have ≥4 verbs."""
    for set_key in ("stem-changers", "go-verbs", "strong-preterite", "spelling-changers"):
        members = d.SETS.get(set_key, [])
        assert len(members) >= 4, (
            f"derived set {set_key!r} has {len(members)} members (need ≥ 4)"
        )
        # All members must be real verbs.
        unknown = [v for v in members if v not in d.VERBS]
        assert not unknown, f"derived set {set_key!r} references unknown verbs: {unknown}"


def test_high_frequency_list_unchanged():
    """The high-frequency verb list must be byte-identical to the frozen 30-verb daily pin.

    This is the primary regression guard for the daily sequence: any reorder or
    addition would shift which verb the daily game selects for every day.
    """
    actual = d.SETS.get("high-frequency", [])
    assert actual == _HIGH_FREQUENCY_FROZEN, (
        f"high-frequency set changed!\n  expected: {_HIGH_FREQUENCY_FROZEN}\n  actual:   {actual}"
    )
