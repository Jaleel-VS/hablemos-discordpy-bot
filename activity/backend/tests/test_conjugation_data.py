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
_SEED = _REPO / "cogs" / "conjugation_cog" / "verb_data.json"


def _seed_verbs() -> set[str]:
    seed = json.loads(_SEED.read_text(encoding="utf-8"))
    return {v for cat in seed["categories"].values() for v in cat["verbs"]}


def test_every_seed_verb_is_present():
    missing = _seed_verbs() - set(d.VERBS)
    assert not missing, f"seed verbs missing from paradigm JSON: {sorted(missing)}"


def test_full_paradigm_grid_for_every_verb():
    # Every verb must carry every configured tense × every canonical pronoun —
    # a missing cell would let pick_question surface an unanswerable prompt.
    incomplete: list[str] = []
    for verb, entry in d.VERBS.items():
        forms = entry["forms"]
        for tense in d.TENSES:
            slot = forms.get(tense)
            if slot is None or any(p not in slot for p in d.PRONOUNS):
                incomplete.append(f"{verb}/{tense}")
    assert not incomplete, f"incomplete paradigm cells: {incomplete}"


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
