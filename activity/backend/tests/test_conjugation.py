"""Tests for the Spanish conjugation game — grading, config, sprint flow.

Run: pytest activity/backend/tests  (from repo root, with the backend venv)
"""
import unicodedata
from datetime import UTC, datetime, timedelta

import pytest
from app.games.base import GameError
from app.games.conjugation import data as d
from app.games.conjugation.engine import ConjugationEngine
from app.games.conjugation.normalize import Match, grade

# ── grading ─────────────────────────────────────────────────────────────────

def test_grade_exact():
    assert grade("hablé", "hablé") == Match.EXACT
    assert grade("  HABLÉ ", "hablé") == Match.EXACT  # case/space tolerant


def test_grade_close_when_only_accent_differs():
    assert grade("hable", "hablé") == Match.CLOSE
    assert grade("comi", "comí") == Match.CLOSE


def test_grade_wrong_stem():
    assert grade("hablo", "hablé") == Match.WRONG
    assert grade("", "hablé") == Match.WRONG


def test_grade_ñ_is_a_letter_not_an_accent():
    # ñ must survive accent-stripping — swapping ñ↔n is WRONG, not CLOSE.
    assert grade("año", "año") == Match.EXACT
    assert grade("ano", "año") == Match.WRONG


def test_grade_normalizes_decomposed_input():
    # Some IMEs / dead-key layouts / paste sources emit NFD (é as e + combining
    # accent, ñ as n + combining tilde). A correctly-typed form in NFD must
    # grade EXACT, not CLOSE (accent) or WRONG (ñ lost to the strip).
    assert grade(unicodedata.normalize("NFD", "hablé"), "hablé") == Match.EXACT
    assert grade(unicodedata.normalize("NFD", "riñó"), "riñó") == Match.EXACT
    # And a genuine accent miss typed in NFD is still CLOSE.
    assert grade(unicodedata.normalize("NFD", "hable"), "hablé") == Match.CLOSE


# ── config resolution (untrusted input) ──────────────────────────────────────

def test_default_config_excludes_vosotros():
    cfg = d.default_config()
    assert "vosotros" not in cfg.pronouns
    assert cfg.verb_set in d.SETS


def test_resolve_config_falls_back_on_garbage():
    cfg = d.resolve_config({"set": "nope", "tenses": ["bogus"], "pronouns": [123]})
    assert cfg.verb_set == d.default_config().verb_set
    assert cfg.tenses == d.default_config().tenses
    assert cfg.pronouns == d.default_config().pronouns


def test_resolve_config_honors_valid_subset():
    cfg = d.resolve_config({"set": "regular-ar", "tenses": ["presente"], "pronouns": ["yo"]})
    assert cfg.verb_set == "regular-ar"
    assert cfg.tenses == ["presente"]
    assert cfg.pronouns == ["yo"]


def test_resolve_config_none_is_default():
    assert d.resolve_config(None).verb_set == d.default_config().verb_set


def test_resolve_config_survives_unhashable_elements():
    # Unhashable elements (lists/dicts) must not raise TypeError on the ``in``
    # membership tests — a hostile /start body degrades to defaults, never 500s.
    base = d.default_config()
    cfg = d.resolve_config(
        {"set": ["x"], "tenses": [["presente"]], "pronouns": [{"a": 1}]}
    )
    assert cfg.verb_set == base.verb_set
    assert cfg.tenses == base.tenses
    assert cfg.pronouns == base.pronouns
    # A single unhashable list as the whole value is fine too.
    assert d.resolve_config({"tenses": [{"nested": True}, "presente"]}).tenses == ["presente"]


# ── sprint flow ───────────────────────────────────────────────────────────

@pytest.fixture
def engine():
    return ConjugationEngine()


def test_new_game_hides_answer_from_client(engine):
    oc = engine.new_game(mode="free", user_id="1")
    assert "prompt" in oc.client_view
    assert "expected" not in oc.client_view["prompt"]  # answer never leaks
    assert "current" not in oc.client_view            # raw state never leaks


def test_correct_answer_scores_and_streaks(engine):
    oc = engine.new_game(mode="free", user_id="1")
    expected = oc.state["current"]["expected"]
    oc2 = engine.submit(state=oc.state, guess=expected)
    assert oc2.client_view["correct"] == 1
    assert oc2.client_view["streak"] == 1
    assert oc2.client_view["last"]["result"] == "exact"


def test_wrong_answer_resets_streak(engine):
    oc = engine.new_game(mode="free", user_id="1")
    oc = engine.submit(state=oc.state, guess=oc.state["current"]["expected"])
    assert oc.client_view["streak"] == 1
    oc = engine.submit(state=oc.state, guess="zzzzz")
    assert oc.client_view["streak"] == 0
    assert oc.client_view["last"]["result"] == "wrong"


def test_deadline_finalizes_game(engine):
    oc = engine.new_game(mode="free", user_id="1")
    state = oc.state
    state["deadline"] = (datetime.now(UTC) - timedelta(seconds=10)).isoformat()
    oc2 = engine.submit(state=state, guess="anything")
    assert engine.is_over(oc2.state)
    assert oc2.client_view["status"] == "over"
    assert "result" in oc2.client_view


def test_submit_after_over_raises(engine):
    oc = engine.new_game(mode="free", user_id="1")
    state = oc.state
    state["status"] = "over"
    with pytest.raises(GameError):
        engine.submit(state=state, guess="x")


def test_hostile_state_rejected(engine):
    with pytest.raises(GameError):
        engine.submit(state={"game": "conjugation"}, guess="x")
    with pytest.raises(GameError):
        engine.submit(state={"game": "wrong"}, guess="x")


def test_result_payload_is_channel_ready(engine):
    oc = engine.new_game(mode="daily", user_id="1")
    # answer two correctly, one wrong
    oc = engine.submit(state=oc.state, guess=oc.state["current"]["expected"])
    oc = engine.submit(state=oc.state, guess=oc.state["current"]["expected"])
    oc = engine.submit(state=oc.state, guess="nope")
    state = oc.state
    state["deadline"] = (datetime.now(UTC) - timedelta(seconds=10)).isoformat()
    oc = engine.submit(state=state, guess="")
    rp = oc.client_view["result"]
    # Shared results-cog contract: won, summary, grid all present.
    assert rp["won"] is True
    assert "Conjugación" in rp["summary"]
    assert rp["grid"]
    assert rp["correct"] == 2
    assert rp["total"] == 3
    assert len(rp["misses"]) == 1


def test_daily_is_deterministic_across_players(engine):
    a = engine.new_game(mode="daily", user_id="alice").client_view["prompt"]
    b = engine.new_game(mode="daily", user_id="bob").client_view["prompt"]
    assert a == b


# ── untimed practice mode ─────────────────────────────────────────────────

def test_daily_is_always_timed(engine):
    view = engine.new_game(mode="daily", user_id="1").client_view
    assert view["timed"] is True
    assert view["deadline"] is not None


def test_freeplay_defaults_to_timed(engine):
    view = engine.new_game(mode="free", user_id="1").client_view
    assert view["timed"] is True
    assert view["deadline"] is not None


def test_untimed_practice_has_no_deadline(engine):
    view = engine.new_game(mode="free", user_id="1", options={"timed": False}).client_view
    assert view["timed"] is False
    assert view["deadline"] is None
    assert view["duration"] is None


def test_untimed_practice_never_expires(engine):
    # A very old start must NOT end an untimed game (no clock to blow).
    oc = engine.new_game(mode="free", user_id="1", options={"timed": False})
    state = oc.state
    state["started_at"] = "2020-01-01T00:00:00+00:00"
    oc2 = engine.submit(state=state, guess=state["current"]["expected"])
    assert not engine.is_over(oc2.state)
    assert oc2.client_view["correct"] == 1


def test_finish_ends_untimed_practice(engine):
    oc = engine.new_game(mode="free", user_id="1", options={"timed": False})
    oc = engine.submit(state=oc.state, guess=oc.state["current"]["expected"])
    oc = engine.submit(state=oc.state, guess="", finish=True)
    assert engine.is_over(oc.state)
    result = oc.client_view["result"]
    assert result["correct"] == 1
    assert result["won"] is True  # completing practice counts for stats


def test_finish_does_not_grade_its_own_guess(engine):
    oc = engine.new_game(mode="free", user_id="1", options={"timed": False})
    before = oc.client_view["answered_count"]
    oc = engine.submit(state=oc.state, guess="whatever", finish=True)
    # finishing must not append a graded answer for the flush call
    assert oc.client_view["result"]["total"] == before
