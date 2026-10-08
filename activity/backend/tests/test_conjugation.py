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


def test_daily_withholds_answer_in_per_answer_feedback(engine):
    # The daily is a fixed shared sequence; revealing each form mid-run would
    # let a player harvest the day's answers. The flag stays, expected does not.
    oc = engine.new_game(mode="daily", user_id="1")
    oc = engine.submit(state=oc.state, guess="definitely-wrong")
    last = oc.client_view["last"]
    assert last["result"] == "wrong"
    assert "expected" not in last
    # ...but the raw sealed state still carries it (the server needs it) and the
    # end-of-game recap discloses the misses.
    assert oc.state["last"]["expected"]


def test_freeplay_reveals_answer_in_feedback(engine):
    oc = engine.new_game(mode="free", user_id="1")
    oc = engine.submit(state=oc.state, guess="definitely-wrong")
    assert oc.client_view["last"]["expected"]  # nothing to game in freeplay


def test_daily_recap_still_lists_missed_answers(engine):
    # Withholding is mid-run only — the recap must still teach the correct forms.
    oc = engine.new_game(mode="daily", user_id="1")
    oc = engine.submit(state=oc.state, guess="nope")
    state = oc.state
    state["deadline"] = (datetime.now(UTC) - timedelta(seconds=10)).isoformat()
    oc = engine.submit(state=state, guess="")
    misses = oc.client_view["result"]["misses"]
    assert misses and misses[0]["expected"]


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


def test_zero_answer_finish_scores_zero_over_zero(engine):
    # Finishing untimed practice with no answers reads "0/0", not a bare "0".
    oc = engine.new_game(mode="free", user_id="1", options={"timed": False})
    oc = engine.submit(state=oc.state, guess="", finish=True)
    rp = oc.client_view["result"]
    assert rp["score"] == "0/0"
    assert rp["total"] == 0


def test_timed_state_with_null_deadline_is_rejected(engine):
    # An incoherent timed+null-deadline state must be rejected up front, not
    # crash later on fromisoformat(None) in the deadline check.
    oc = engine.new_game(mode="free", user_id="1")  # timed
    state = oc.state
    state["deadline"] = None
    with pytest.raises(GameError):
        engine.submit(state=state, guess="x")


def test_early_finish_on_timed_game_is_rejected(engine):
    # A timed daily can't be ended instantly to bank a 0-answer streak day.
    oc = engine.new_game(mode="daily", user_id="1")
    with pytest.raises(GameError):
        engine.submit(state=oc.state, guess="", finish=True)
    assert not engine.is_over(oc.state)


def test_end_of_timer_flush_still_finishes_timed_game(engine):
    # The legit end-of-timer flush (finish arriving at/after the deadline) is
    # accepted and finalizes the run.
    oc = engine.new_game(mode="free", user_id="1")  # timed sprint
    state = oc.state
    state["deadline"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    oc = engine.submit(state=state, guess="", finish=True)
    assert engine.is_over(oc.state)
    assert "result" in oc.client_view


# ── new Contract behaviour ────────────────────────────────────────────────

def test_daily_tenses_pinned_regardless_of_data_tenses(engine, monkeypatch):
    """Daily config must stay on the 4 pinned tenses even if TENSES grows."""
    extra = dict(d.TENSES)
    extra["condicional"] = "Condicional"
    monkeypatch.setattr(d, "TENSES", extra)
    oc = engine.new_game(mode="daily", user_id="1")
    cfg = d.Config.from_state(oc.state["config"])
    assert cfg.tenses == ["presente", "pretérito", "imperfecto", "futuro"]
    assert "condicional" not in cfg.tenses


def test_strict_close_scores_like_wrong(engine):
    """In strict mode a CLOSE result must NOT increment correct or streak."""
    oc = engine.new_game(mode="free", user_id="1", options={"timed": False, "strict": True})
    # Pin an accented form so the de-accented guess is deterministically CLOSE.
    oc.state["current"] = d.make_question("hablar", "pretérito", "yo").as_state()
    assert oc.state["current"]["expected"] == "hablé"
    oc2 = engine.submit(state=oc.state, guess="hable")
    assert oc2.client_view["last"]["result"] == "close"
    assert oc2.client_view["correct"] == 0   # strict: close doesn't score
    assert oc2.client_view["streak"] == 0    # strict: streak resets
    assert oc2.client_view["awaiting_retry"] is True  # still a miss → retry


def test_skip_recorded_streak_reset_and_excluded_from_total(engine):
    """Skip records an entry, resets streak, and excludes from accuracy total."""
    oc = engine.new_game(mode="free", user_id="1", options={"timed": False})
    # Answer one correctly first.
    oc = engine.submit(state=oc.state, guess=oc.state["current"]["expected"])
    assert oc.client_view["streak"] == 1
    # Now skip.
    oc = engine.submit(state=oc.state, guess="", action="skip")
    assert oc.client_view["streak"] == 0
    assert oc.client_view["answered_count"] == 2
    # Finish and verify total excludes the skip.
    oc = engine.submit(state=oc.state, guess="", finish=True)
    rp = oc.client_view["result"]
    assert rp["total"] == 1        # skip not counted
    assert rp["skipped"] == 1
    assert rp["correct"] == 1
    assert rp["score"] == "1/1"


def test_skip_not_allowed_while_awaiting_retry(engine):
    """Skip raises GameError when awaiting_retry is True."""
    oc = engine.new_game(mode="free", user_id="1", options={"timed": False})
    # Submit a wrong answer to enter awaiting_retry.
    oc = engine.submit(state=oc.state, guess="zzzzz")
    assert oc.client_view["awaiting_retry"] is True
    with pytest.raises(GameError):
        engine.submit(state=oc.state, guess="", action="skip")


def test_retry_flow_wrong_in_untimed_enters_retry_mode(engine):
    """Wrong answer in untimed free mode sets awaiting_retry; same prompt stays."""
    oc = engine.new_game(mode="free", user_id="1", options={"timed": False})
    expected_verb = oc.state["current"]["verb"]
    oc = engine.submit(state=oc.state, guess="zzzzz")
    view = oc.client_view
    assert view["awaiting_retry"] is True
    assert view["last"]["result"] == "wrong"
    # Prompt must be the same question.
    assert view["prompt"]["verb"] == expected_verb
    # Counts unchanged.
    assert view["correct"] == 0


def test_retry_exact_advances_and_keeps_score(engine):
    """Typing the correct form on retry clears awaiting_retry and advances."""
    oc = engine.new_game(mode="free", user_id="1", options={"timed": False})
    correct = oc.state["current"]["expected"]
    # First wrong.
    oc = engine.submit(state=oc.state, guess="zzzzz")
    assert oc.client_view["awaiting_retry"] is True
    before_seq = oc.state["seq"]
    # Retry correctly.
    oc = engine.submit(state=oc.state, guess=correct, action="retry")
    assert oc.client_view["awaiting_retry"] is False
    # Score NOT changed by the retry (wrong already logged, no extra credit).
    assert oc.client_view["correct"] == 0
    # Advanced to a new prompt.
    assert oc.state["seq"] == before_seq + 1


def test_retry_two_failed_retries_advances_anyway(engine):
    """After _MAX_RETRY_ATTEMPTS (2) failed retries the prompt advances."""
    oc = engine.new_game(mode="free", user_id="1", options={"timed": False})
    # Enter retry mode.
    oc = engine.submit(state=oc.state, guess="zzzzz")
    assert oc.client_view["awaiting_retry"] is True
    before_seq = oc.state["seq"]
    # First failed retry.
    oc = engine.submit(state=oc.state, guess="zzzzz", action="retry")
    assert oc.client_view["awaiting_retry"] is True
    assert oc.state["retry_attempts"] == 1
    # Second failed retry — should advance.
    oc = engine.submit(state=oc.state, guess="zzzzz", action="retry")
    assert oc.client_view["awaiting_retry"] is False
    assert oc.state["seq"] == before_seq + 1


def test_timed_mode_never_awaits_retry(engine):
    """In timed mode (default) a wrong answer never sets awaiting_retry."""
    oc = engine.new_game(mode="free", user_id="1")  # default = timed
    oc = engine.submit(state=oc.state, guess="zzzzz")
    assert oc.client_view["awaiting_retry"] is False
    # The game should have advanced (seq incremented).
    assert oc.state["seq"] == 1


def test_items_autofinish_at_n(engine):
    """Untimed set mode auto-finishes when answered count reaches items."""
    items = 2
    oc = engine.new_game(
        mode="free", user_id="1",
        options={"timed": False, "items": items, "pronouns": ["yo"]},
    )
    assert oc.client_view["items"] == items
    assert oc.client_view["remaining_items"] == items
    # Answer `items` questions correctly.
    for _ in range(items):
        assert oc.client_view["status"] == "playing"
        oc = engine.submit(state=oc.state, guess=oc.state["current"]["expected"])
    assert oc.client_view["status"] == "over"
    assert "result" in oc.client_view


def test_breakdown_totals_exclude_skipped(engine):
    """Tense/pronoun breakdown totals must not count skipped entries."""
    oc = engine.new_game(mode="free", user_id="1", options={"timed": False})
    # Skip one.
    oc = engine.submit(state=oc.state, guess="", action="skip")
    # Answer one correctly.
    oc = engine.submit(state=oc.state, guess=oc.state["current"]["expected"])
    oc = engine.submit(state=oc.state, guess="", finish=True)
    rp = oc.client_view["result"]
    # Each tense total in breakdown must be ≤ total (excluding skips).
    for tense_stats in rp["breakdown"]["tenses"].values():
        assert tense_stats["total"] <= rp["total"]
    # Sum of all tense totals == total answered (excluding skips).
    tense_sum = sum(v["total"] for v in rp["breakdown"]["tenses"].values())
    assert tense_sum == rp["total"]


def test_review_verbs_distinct_and_capped(engine):
    """review_verbs must have distinct verbs, capped at MAX_REVIEW_VERBS."""
    oc = engine.new_game(mode="free", user_id="1", options={"timed": False})
    # Produce some misses (wrong answers).
    for _ in range(3):
        oc = engine.submit(state=oc.state, guess="zzzzz")
        if oc.client_view["awaiting_retry"]:
            oc = engine.submit(state=oc.state, guess="zzzzz", action="retry")
            oc = engine.submit(state=oc.state, guess="zzzzz", action="retry")
    oc = engine.submit(state=oc.state, guess="", finish=True)
    rp = oc.client_view["result"]
    review = rp["review_verbs"]
    assert len(review) == len(set(review))          # distinct
    assert len(review) <= d.MAX_REVIEW_VERBS        # capped


def test_daily_withholds_note_and_row(engine):
    """Daily mode must not expose note or row in per-answer feedback."""
    oc = engine.new_game(mode="daily", user_id="1")
    oc = engine.submit(state=oc.state, guess="definitely-wrong")
    last = oc.client_view["last"]
    assert "note" not in last
    assert "row" not in last
    # Raw state still carries them for the recap.
    assert "expected" in oc.state["last"]


def test_freeplay_includes_note_and_row_in_feedback(engine):
    """Free mode must include note and row in per-answer feedback."""
    oc = engine.new_game(mode="free", user_id="1", options={"timed": False})
    oc = engine.submit(state=oc.state, guess="zzzzz")
    last = oc.client_view["last"]
    assert "note" in last
    assert "row" in last


def test_result_payload_has_new_fields(engine):
    """result_payload must carry skipped, close, strict, breakdown, review_verbs."""
    oc = engine.new_game(mode="free", user_id="1", options={"timed": False})
    oc = engine.submit(state=oc.state, guess="", finish=True)
    rp = oc.client_view["result"]
    assert "skipped" in rp
    assert "close" in rp
    assert "strict" in rp
    assert "breakdown" in rp
    assert "tenses" in rp["breakdown"]
    assert "pronouns" in rp["breakdown"]
    assert "review_verbs" in rp


def test_config_stored_and_restored_with_full_fields(engine):
    """Config round-trips through state with strict/variants/items/verbs_override."""
    oc = engine.new_game(
        mode="free", user_id="1",
        options={"timed": False, "strict": True, "variants": False, "items": 5},
    )
    cfg = d.Config.from_state(oc.state["config"])
    assert cfg.strict is True
    assert cfg.items == 5


def test_invalid_action_raises(engine):
    """submit must raise GameError for an unrecognized action."""
    oc = engine.new_game(mode="free", user_id="1", options={"timed": False})
    with pytest.raises(GameError):
        engine.submit(state=oc.state, guess="x", action="teleport")


def test_retry_action_without_awaiting_raises(engine):
    """retry action raises GameError when awaiting_retry is False."""
    oc = engine.new_game(mode="free", user_id="1", options={"timed": False})
    with pytest.raises(GameError):
        engine.submit(state=oc.state, guess="x", action="retry")


def test_client_view_has_items_and_remaining(engine):
    """client_view must include items and remaining_items for untimed set mode."""
    oc = engine.new_game(
        mode="free", user_id="1",
        options={"timed": False, "items": 3, "pronouns": ["yo"]},
    )
    view = oc.client_view
    assert view["items"] == 3
    assert view["remaining_items"] == 3
