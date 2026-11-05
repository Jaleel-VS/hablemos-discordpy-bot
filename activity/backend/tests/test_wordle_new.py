"""Behaviour tests for W1–W5 Wordle engine changes.

Covers:
- W1  result_payload includes learning_card on win and loss
- learning cards match the committed corpus on both win and loss
- W4  hint appears in client_view after 3 non-winning freeplay guesses
- W4  hint absent in daily mode
- W4  hint absent before 3 guesses
- W5  FREE_ANSWERS excludes retired words
- W5  daily_answer unchanged for a fixed date (byte-stable daily list)
- W5  freeplay draws from FREE_ANSWERS only
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from app.games.wordle import daily as daily_mod
from app.games.wordle.engine import WordleEngine
from app.games.wordle.words import ANSWERS, FREE_ANSWERS, is_valid_guess


def _committed_card(answer: str) -> dict:
    path = Path(__file__).resolve().parent.parent / "app" / "games" / "data" / "wordle_lexicon.json"
    return json.loads(path.read_text(encoding="utf-8"))[answer]


def _make_free_game(engine: WordleEngine, answer: str) -> dict:
    """Start a freeplay game and patch the answer in so we control it."""
    outcome = engine.new_game(mode="free", user_id="u1")
    state = dict(outcome.state)
    state["answer"] = answer
    return state


def _wrong_guess(answer: str) -> str:
    """Return a valid guess that is not the answer."""
    for w in ANSWERS:
        if w != answer and is_valid_guess(w):
            return w
    raise RuntimeError("no valid non-answer guess found")





def test_result_has_learning_card_on_win():
    answer = ANSWERS[0]
    engine = WordleEngine()
    state = _make_free_game(engine, answer)
    result = engine.submit(state=state, guess=answer).client_view["result"]
    assert result["won"] is True
    assert result["learning_card"] == _committed_card(answer)


def test_result_has_learning_card_on_loss():
    answer = ANSWERS[1]
    engine = WordleEngine()
    state = _make_free_game(engine, answer)
    wrong = _wrong_guess(answer)
    for _ in range(6):
        out = engine.submit(state=state, guess=wrong)
        state = out.state
    result = out.client_view["result"]
    assert result["won"] is False
    assert result["learning_card"] == _committed_card(answer)


def test_result_no_learning_card_when_missing():
    engine = WordleEngine()
    state = engine.new_game(mode="free", user_id="u1").state
    state.update(answer="not-in-the-committed-lexicon", status="lost")
    result = engine.client_view(state)["result"]
    assert result["won"] is False
    assert "learning_card" not in result


def test_hint_appears_after_3_freeplay_misses():
    answer = ANSWERS[3]

    engine = WordleEngine()
    state = _make_free_game(engine, answer)
    wrong = _wrong_guess(answer)

    for _ in range(2):
        out = engine.submit(state=state, guess=wrong)
        state = out.state
        assert "hint" not in out.client_view, "hint must not appear before 3 misses"

    out = engine.submit(state=state, guess=wrong)
    state = out.state
    view = out.client_view
    assert "hint" in view
    card = _committed_card(answer)
    assert view["hint"] == {"en": card["en"], "pos": card["pos"]}




def test_hint_absent_in_daily():
    answer = ANSWERS[5]

    engine = WordleEngine()
    outcome = engine.new_game(mode="daily", user_id="u1")
    state = dict(outcome.state)
    state["answer"] = answer
    wrong = _wrong_guess(answer)
    for _ in range(3):
        out = engine.submit(state=state, guess=wrong)
        state = out.state
        assert "hint" not in out.client_view, "daily must never have hint"



def test_retired_words_not_in_free_answers():
    """Every word in the retired list must be absent from FREE_ANSWERS."""
    data_dir = Path(__file__).resolve().parent.parent / "app" / "games" / "data"
    retired = {
        ln.strip()
        for ln in (data_dir / "wordle_answers_retired.txt").read_text().splitlines()
        if ln.strip() and not ln.startswith("#")
    }
    free_set = set(FREE_ANSWERS)
    leaked = retired & free_set
    assert not leaked, f"retired words leaked into FREE_ANSWERS: {leaked}"


def test_retired_words_still_in_answers():
    """Retired words remain in the daily ANSWERS list (daily stability)."""
    data_dir = Path(__file__).resolve().parent.parent / "app" / "games" / "data"
    retired = {
        ln.strip()
        for ln in (data_dir / "wordle_answers_retired.txt").read_text().splitlines()
        if ln.strip() and not ln.startswith("#")
    }
    answers_set = set(ANSWERS)
    missing = retired - answers_set
    assert not missing, f"retired words not found in ANSWERS: {missing}"


def test_daily_answer_unchanged_for_fixed_date():
    """Daily answer for 2026-02-10 must be the same word every run (byte-stable)."""
    fixed = date(2026, 2, 10)
    word, puzzle_no = daily_mod.daily_answer(fixed)
    # Re-derive independently to confirm no mutation.
    idx = (fixed - date(2026, 1, 1)).days % len(ANSWERS)
    assert word == ANSWERS[idx]
    assert puzzle_no == (fixed - date(2026, 1, 1)).days + 1


def test_freeplay_draws_from_free_answers():
    """new_game free mode must only ever return FREE_ANSWERS words."""
    free_set = set(FREE_ANSWERS)

    seen = set()
    # Sample 30 random choices via the engine to confirm none are retired.
    engine = WordleEngine()
    for _ in range(30):
        outcome = engine.new_game(mode="free", user_id="u1")
        seen.add(outcome.state["answer"])

    # We can't exhaustively test randomness but ensure all seen words are valid.
    outside = seen - free_set
    assert not outside, f"freeplay returned non-FREE_ANSWERS words: {outside}"
