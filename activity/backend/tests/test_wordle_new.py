"""Behaviour tests for W1–W5 Wordle engine changes.

Covers:
- W1  result_payload includes learning_card on win and loss
- W1  learning_card absent when lexicon missing entry
- W4  hint appears in client_view after 3 non-winning freeplay guesses
- W4  hint absent in daily mode
- W4  hint absent before 3 guesses
- W5  FREE_ANSWERS excludes retired words
- W5  daily_answer unchanged for a fixed date (byte-stable daily list)
- W5  freeplay draws from FREE_ANSWERS only
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from app.games.wordle import daily as daily_mod
from app.games.wordle.engine import WordleEngine
from app.games.wordle.words import ANSWERS, FREE_ANSWERS, is_valid_guess

# ── helpers ───────────────────────────────────────────────────────────────────

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


def _force_game_over(engine: WordleEngine, mode: str, *, won: bool) -> dict:
    """Return a finished state for the given answer."""
    outcome = engine.new_game(mode=mode, user_id="u1")  # type: ignore[arg-type]
    state = outcome.state
    answer = state["answer"]
    if won:
        # One correct guess finishes it.
        result = engine.submit(state=state, guess=answer)
        return result.state
    # Six wrong guesses.
    wrong = _wrong_guess(answer)
    for _ in range(6):
        result = engine.submit(state=state, guess=wrong)
        state = result.state
    return state


# ── W1: learning card in result_payload ───────────────────────────────────────

def test_result_has_learning_card_on_win(tmp_path, monkeypatch):
    """learning_card present in result_payload after a win."""
    answer = ANSWERS[0]
    fake_card = {
        "display": answer, "pos": "noun", "en": "test gloss",
        "example_es": f"Frase con {answer}.", "example_en": "Test sentence.",
        "lemma": answer, "form": "",
    }
    # Patch lexicon to return a known card.
    monkeypatch.setattr("app.games.wordle.engine._lexicon", lambda: {answer: fake_card})

    engine = WordleEngine()
    state = _make_free_game(engine, answer)
    result_state = engine.submit(state=state, guess=answer).state

    payload = engine.result_payload(result_state)
    assert payload["won"] is True
    assert "learning_card" in payload
    assert payload["learning_card"]["en"] == "test gloss"


def test_result_has_learning_card_on_loss(monkeypatch):
    """learning_card present in result_payload after a loss."""
    answer = ANSWERS[1]
    fake_card = {
        "display": answer, "pos": "verb", "en": "loss gloss",
        "example_es": f"Ejemplo con {answer}.", "example_en": "Example.",
        "lemma": answer, "form": "",
    }
    monkeypatch.setattr("app.games.wordle.engine._lexicon", lambda: {answer: fake_card})

    engine = WordleEngine()
    state = _make_free_game(engine, answer)
    wrong = _wrong_guess(answer)
    for _ in range(6):
        out = engine.submit(state=state, guess=wrong)
        state = out.state

    payload = engine.result_payload(state)
    assert payload["won"] is False
    assert "learning_card" in payload
    assert payload["learning_card"]["en"] == "loss gloss"


def test_result_no_learning_card_when_missing(monkeypatch):
    """learning_card absent when lexicon has no entry for the answer."""
    monkeypatch.setattr("app.games.wordle.engine._lexicon", lambda: {})

    engine = WordleEngine()
    answer = ANSWERS[2]
    state = _make_free_game(engine, answer)
    result_state = engine.submit(state=state, guess=answer).state

    payload = engine.result_payload(result_state)
    assert "learning_card" not in payload


# ── W4: freeplay hint ─────────────────────────────────────────────────────────

def test_hint_appears_after_3_freeplay_misses(monkeypatch):
    """Freeplay client_view includes hint after exactly 3 wrong guesses."""
    answer = ANSWERS[3]
    fake_card = {
        "display": answer, "pos": "noun", "en": "hint gloss",
        "example_es": f"Con {answer}.", "example_en": "With it.",
        "lemma": answer, "form": "",
    }
    monkeypatch.setattr("app.games.wordle.engine._lexicon", lambda: {answer: fake_card})

    engine = WordleEngine()
    state = _make_free_game(engine, answer)
    wrong = _wrong_guess(answer)

    # 2 guesses: no hint yet.
    for _ in range(2):
        out = engine.submit(state=state, guess=wrong)
        state = out.state
        assert "hint" not in out.client_view, "hint must not appear before 3 misses"

    # 3rd guess: hint should appear.
    out = engine.submit(state=state, guess=wrong)
    state = out.state
    view = out.client_view
    assert "hint" in view
    assert view["hint"]["en"] == "hint gloss"
    assert view["hint"]["pos"] == "noun"


def test_hint_absent_before_3_guesses(monkeypatch):
    """Hint absent with fewer than 3 guesses, even with a lexicon entry."""
    answer = ANSWERS[4]
    fake_card = {
        "display": answer, "pos": "verb", "en": "early gloss",
        "example_es": f"Con {answer}.", "example_en": "With it.",
        "lemma": answer, "form": "",
    }
    monkeypatch.setattr("app.games.wordle.engine._lexicon", lambda: {answer: fake_card})

    engine = WordleEngine()
    state = _make_free_game(engine, answer)
    wrong = _wrong_guess(answer)

    out = engine.submit(state=state, guess=wrong)
    assert "hint" not in out.client_view

    out2 = engine.submit(state=out.state, guess=wrong)
    assert "hint" not in out2.client_view


def test_hint_absent_in_daily(monkeypatch):
    """Daily mode never receives a hint, even after 3 misses."""
    answer = ANSWERS[5]
    fake_card = {
        "display": answer, "pos": "noun", "en": "daily gloss",
        "example_es": f"Con {answer}.", "example_en": "With it.",
        "lemma": answer, "form": "",
    }
    monkeypatch.setattr("app.games.wordle.engine._lexicon", lambda: {answer: fake_card})

    engine = WordleEngine()
    outcome = engine.new_game(mode="daily", user_id="u1")
    state = dict(outcome.state)
    # Patch in a word we know is in the lexicon.
    state["answer"] = answer
    wrong = _wrong_guess(answer)
    for _ in range(3):
        out = engine.submit(state=state, guess=wrong)
        state = out.state
        assert "hint" not in out.client_view, "daily must never have hint"


# ── W5: FREE_ANSWERS / daily stability ────────────────────────────────────────

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
