"""Tests for the cloze (fill-in-the-blank) game — data, config, round flow.

Run: pytest activity/backend/tests  (from repo root, with the backend venv)

Mirrors the shape of test_conjugation.py: it exercises grading (reused from the
conjugation normalizer), config resolution/normalization, the round flow,
daily determinism + answer-withholding, and hostile-state guards. It also
guards the committed content JSON so a bad regeneration can't silently ship.
"""
import copy

import pytest
from app.games.base import GameError
from app.games.cloze import data as d
from app.games.cloze.engine import ROUND_SIZE, ClozeEngine

# ── committed content integrity ───────────────────────────────────────────

def test_data_loaded():
    assert d._ALL_CARDS, "cloze_sentences.json should be present and non-empty"
    assert "es" in d.TARGETS
    assert set(d.DIFFICULTIES) >= {"beginner", "intermediate", "advanced"}


def test_every_card_is_well_formed():
    for c in d._ALL_CARDS:
        assert c["cloze"].count("___") == 1, f"{c['id']} must have exactly one blank"
        assert isinstance(c["distractors"], list) and len(c["distractors"]) == 3
        answer_lower = c["answer"].lower()
        assert answer_lower not in {x.lower() for x in c["distractors"]}
        assert c["target"] in d.TARGETS
        assert c["difficulty"] in d.DIFFICULTIES
        assert c["context"].strip()


def test_both_decks_have_enough_for_a_round():
    for target in d.TARGETS:
        assert len(d._BY_TARGET[target]) >= ROUND_SIZE


# ── config resolution ──────────────────────────────────────────────────────

def test_default_config_is_spanish_mixed():
    cfg = d.default_config()
    assert cfg.target == "es"
    assert cfg.difficulty is None
    assert cfg.pool  # non-empty


def test_resolve_config_falls_back_on_garbage():
    cfg = d.resolve_config({"target": "nope", "difficulty": "bogus"})
    assert cfg.target == d.default_config().target
    assert cfg.difficulty is None


def test_resolve_config_honors_valid_values():
    cfg = d.resolve_config({"target": "en", "difficulty": "beginner"})
    assert cfg.target == "en"
    assert cfg.difficulty == "beginner"


def test_resolve_config_none_is_default():
    assert d.resolve_config(None).target == d.default_config().target


def test_resolve_config_survives_unhashable_elements():
    # A hostile /start body must degrade to defaults, never raise.
    cfg = d.resolve_config({"target": ["x"], "difficulty": {"a": 1}})
    assert cfg.target == d.default_config().target
    assert cfg.difficulty is None


def test_pool_never_empty_for_sparse_difficulty():
    # Even if a difficulty were sparse, .pool must not return empty.
    cfg = d.Config(target="es", difficulty="beginner")
    assert cfg.pool


# ── card selection ──────────────────────────────────────────────────────────

def test_deterministic_cards_are_stable_and_distinct():
    cfg = d.daily_config()
    a = d.deterministic_cards(cfg, seed=214, count=ROUND_SIZE)
    b = d.deterministic_cards(cfg, seed=214, count=ROUND_SIZE)
    assert [c.id for c in a] == [c.id for c in b]  # reproducible
    assert len({c.id for c in a}) == len(a)        # no repeats within a round


def test_deterministic_cards_differ_by_seed():
    cfg = d.daily_config()
    a = d.deterministic_cards(cfg, seed=1, count=ROUND_SIZE)
    b = d.deterministic_cards(cfg, seed=2, count=ROUND_SIZE)
    assert [c.id for c in a] != [c.id for c in b]


def test_random_cards_are_distinct():
    cfg = d.default_config()
    cards = d.random_cards(cfg, count=ROUND_SIZE)
    assert len({c.id for c in cards}) == len(cards)


def test_options_include_answer_and_are_stable():
    card = d.random_cards(d.default_config(), count=1)[0]
    opts = card.options(seed="abc")
    assert card.answer in opts
    assert len(opts) == 4
    assert card.options(seed="abc") == opts  # stable for same seed
    for dstr in card.distractors:
        assert dstr in opts


# ── round flow ──────────────────────────────────────────────────────────────

@pytest.fixture
def engine():
    return ClozeEngine()


def test_new_game_hides_answer_from_client(engine):
    oc = engine.new_game(mode="free", user_id="1", options={"answer_mode": "type"})
    assert "prompt" in oc.client_view
    assert "answer" not in oc.client_view["prompt"]  # answer never leaks
    assert "cards" not in oc.client_view             # raw state never leaks


def test_choice_prompt_exposes_options(engine):
    oc = engine.new_game(mode="free", user_id="1", options={"answer_mode": "choice"})
    prompt = oc.client_view["prompt"]
    assert len(prompt["options"]) == 4
    # The answer must be one of the options (it's needed to be pickable).
    answer = oc.state["cards"][0]["answer"]
    assert answer in prompt["options"]


def test_correct_answer_scores_and_streaks(engine):
    oc = engine.new_game(mode="free", user_id="1", options={"answer_mode": "type"})
    answer = oc.state["cards"][0]["answer"]
    oc2 = engine.submit(state=oc.state, guess=answer)
    assert oc2.client_view["correct"] == 1
    assert oc2.client_view["streak"] == 1
    assert oc2.client_view["last"]["result"] == "exact"


def test_wrong_answer_breaks_streak(engine):
    oc = engine.new_game(mode="free", user_id="1", options={"answer_mode": "type"})
    a0 = oc.state["cards"][0]["answer"]
    oc = engine.submit(state=oc.state, guess=a0)  # correct → streak 1
    assert oc.client_view["streak"] == 1
    oc = engine.submit(state=oc.state, guess="definitely-wrong-xyz")
    assert oc.client_view["streak"] == 0
    assert oc.client_view["last"]["result"] == "wrong"


def test_accent_only_miss_is_close(engine):
    # Find a card whose answer carries an accent so we can test the CLOSE tier.
    oc = engine.new_game(mode="free", user_id="1", options={"answer_mode": "type"})
    # Force a known accented answer into the current card for a deterministic test.
    accented = "café"
    oc.state["cards"][oc.state["seq"]]["answer"] = accented
    oc2 = engine.submit(state=oc.state, guess="cafe")
    assert oc2.client_view["last"]["result"] == "close"
    assert oc2.client_view["correct"] == 1  # close still counts


def test_round_ends_after_round_size_cards(engine):
    oc = engine.new_game(mode="free", user_id="1", options={"answer_mode": "choice"})
    state = oc.state
    for _ in range(ROUND_SIZE):
        assert not engine.is_over(state)
        cur = state["cards"][state["seq"]]
        state = engine.submit(state=state, guess=cur["answer"]).state
    assert engine.is_over(state)
    result = engine.result_payload(state)
    assert result["score"] == f"{ROUND_SIZE}/{ROUND_SIZE}"
    assert result["won"] is True


def test_finish_ends_round_early(engine):
    oc = engine.new_game(mode="free", user_id="1", options={"answer_mode": "type"})
    oc2 = engine.submit(state=oc.state, guess="", finish=True)
    assert engine.is_over(oc2.state)
    assert oc2.client_view["last"] is None


def test_daily_early_finish_is_rejected(engine):
    # The daily feeds streaks; ending it early must not bank a completed-daily
    # win/streak for a partial run. An early daily finish is rejected.
    oc = engine.new_game(mode="daily", user_id="1", options={})
    with pytest.raises(GameError):
        engine.submit(state=oc.state, guess="", finish=True)
    # And answering all cards then finishing is unnecessary but harmless (the
    # round already ended on the last answer).
    state = oc.state
    for _ in range(ROUND_SIZE):
        cur = state["cards"][state["seq"]]
        state = engine.submit(state=state, guess=cur["answer"]).state
    assert engine.is_over(state)


def test_daily_expires_next_day(engine):
    # A daily token whose date is no longer today must be rejected (stale
    # puzzle can't be finished later to credit a streak).
    oc = engine.new_game(mode="daily", user_id="1", options={})
    oc.state["date"] = "2020-01-01"  # force an expired daily
    with pytest.raises(GameError):
        engine.submit(state=oc.state, guess="whatever")


def test_type_mode_hides_options(engine):
    # In type-in mode the options contain the answer, so they must NOT appear in
    # the client view (that would hand over the answer).
    oc = engine.new_game(mode="free", user_id="1", options={"answer_mode": "type"})
    assert "options" not in oc.client_view["prompt"]


def test_submit_after_over_is_rejected(engine):
    oc = engine.new_game(mode="free", user_id="1")
    over = engine.submit(state=oc.state, guess="", finish=True).state
    with pytest.raises(GameError):
        engine.submit(state=over, guess="x")


# ── daily determinism + anti-harvest ────────────────────────────────────────

def test_daily_is_deterministic_across_users(engine):
    a = engine.new_game(mode="daily", user_id="1", options={})
    b = engine.new_game(mode="daily", user_id="2", options={})
    assert [c["id"] for c in a.state["cards"]] == [c["id"] for c in b.state["cards"]]
    assert a.state["puzzle_no"] == b.state["puzzle_no"]


def test_daily_withholds_all_feedback(engine):
    # The daily is a deterministic shared sequence and state round-trips as a
    # sealed token, so ANY grading signal — the per-card result flag OR the
    # running counters — lets a choice-mode player replay the previous turn's
    # token and probe options. Daily play therefore returns no per-card feedback
    # AND withholds correct/streak/best_streak; everything is disclosed only in
    # the end-of-round recap.
    oc = engine.new_game(mode="daily", user_id="1", options={"answer_mode": "choice"})
    answer = oc.state["cards"][0]["answer"]
    oc2 = engine.submit(state=oc.state, guess=answer)
    view = oc2.client_view
    assert view["last"] is None          # no answer AND no result flag
    assert view["correct"] is None       # counters withheld during daily play
    assert view["streak"] is None
    assert view["best_streak"] is None
    # Progress still advances (leaks nothing about the current card's answer).
    assert view["answered_count"] == 1
    # The internal state still tracks the real score for the recap.
    assert oc2.state["correct"] == 1


def test_daily_replay_oracle_is_closed(engine):
    # Direct regression for the round-3 advisor finding: replaying the SAME
    # daily token against each of the 4 choice options must yield byte-for-byte
    # identical client views. If any field (result flag, counters, or anything
    # else) differed by which option was guessed, that field would itself be
    # the replay oracle — the attacker never needs the withheld answer, only a
    # field that varies with the guess.
    oc = engine.new_game(mode="daily", user_id="1", options={"answer_mode": "choice"})
    options = oc.client_view["prompt"]["options"]
    assert len(options) == 4
    views = []
    for opt in options:
        state_copy = copy.deepcopy(oc.state)
        outcome = engine.submit(state=state_copy, guess=opt)
        views.append(outcome.client_view)
    assert all(v == views[0] for v in views), (
        "daily client_view must not vary with the guessed option "
        f"(replay oracle reopened): {views}"
    )


def test_freeplay_shows_live_counters(engine):
    # Freeplay has no streak stakes, so the live score is shown during play.
    oc = engine.new_game(mode="free", user_id="1", options={"answer_mode": "choice"})
    answer = oc.state["cards"][0]["answer"]
    oc2 = engine.submit(state=oc.state, guess=answer)
    assert oc2.client_view["correct"] == 1


def test_daily_recap_reveals_counters(engine):
    # Once the daily round is over, the recap (and top-level counters) disclose
    # the real score — there's no more token to replay.
    oc = engine.new_game(mode="daily", user_id="1", options={"answer_mode": "choice"})
    state = oc.state
    for _ in range(ROUND_SIZE):
        cur = state["cards"][state["seq"]]
        state = engine.submit(state=state, guess=cur["answer"]).state
    view = engine.client_view(state)
    assert view["correct"] == ROUND_SIZE
    assert view["result"]["score"] == f"{ROUND_SIZE}/{ROUND_SIZE}"


def test_freeplay_reveals_answer_in_feedback(engine):
    oc = engine.new_game(mode="free", user_id="1", options={"answer_mode": "type"})
    oc2 = engine.submit(state=oc.state, guess="wrong-answer-here")
    assert "answer" in oc2.client_view["last"]


def test_recap_exposes_misses_with_answers(engine):
    oc = engine.new_game(mode="daily", user_id="1", options={"answer_mode": "type"})
    state = oc.state
    for _ in range(ROUND_SIZE):
        if engine.is_over(state):
            break
        state = engine.submit(state=state, guess="wrong-xyz").state
    result = engine.result_payload(state)
    assert len(result["misses"]) == ROUND_SIZE
    # The recap discloses the correct answer for review (unlike mid-run daily).
    assert all("answer" in m for m in result["misses"])


def test_empty_guess_is_rejected(engine):
    # An empty (non-finish) guess must not be graded/advanced — otherwise a
    # client could walk a daily to a persisted won=True 0/N without answering.
    oc = engine.new_game(mode="daily", user_id="1", options={"answer_mode": "type"})
    with pytest.raises(GameError):
        engine.submit(state=oc.state, guess="")
    with pytest.raises(GameError):
        engine.submit(state=oc.state, guess="   ")
    # State did not advance.
    assert oc.state["seq"] == 0
    assert oc.state["answered"] == []


def test_recap_includes_close_answers_for_correction(engine):
    # A CLOSE (accent) answer counts as correct but the learner still needs to
    # see the right spelling; in daily mode there's no mid-run feedback, so the
    # recap must include CLOSE entries (with their correct answer), not only
    # outright WRONG ones.
    oc = engine.new_game(mode="daily", user_id="1", options={"answer_mode": "type"})
    state = oc.state
    # Force a known accented answer and submit the accent-stripped form (CLOSE).
    state["cards"][0]["answer"] = "caf\u00e9"
    state = engine.submit(state=state, guess="cafe").state
    for _ in range(ROUND_SIZE - 1):
        if engine.is_over(state):
            break
        cur = state["cards"][state["seq"]]
        state = engine.submit(state=state, guess=cur["answer"]).state
    result = engine.result_payload(state)
    close = [m for m in result["misses"] if m["result"] == "close"]
    assert len(close) == 1
    assert close[0]["answer"] == "caf\u00e9"


# ── hostile state guards ────────────────────────────────────────────────────

def test_validate_rejects_wrong_game(engine):
    with pytest.raises(GameError):
        engine.submit(state={"game": "wordle", "status": "playing"}, guess="x")


def test_validate_rejects_missing_cards(engine):
    bad = {"game": "cloze", "status": "playing", "answered": [], "seq": 0}
    with pytest.raises(GameError):
        engine.submit(state=bad, guess="x")


def test_validate_rejects_out_of_range_seq(engine):
    oc = engine.new_game(mode="free", user_id="1")
    state = oc.state
    state["seq"] = 999  # past the end while still "playing"
    with pytest.raises(GameError):
        engine.submit(state=state, guess="x")


def test_validate_rejects_non_dict_state(engine):
    with pytest.raises(GameError):
        engine.submit(state="not a dict", guess="x")  # type: ignore[arg-type]


def test_validate_rejects_non_int_counters(engine):
    oc = engine.new_game(mode="free", user_id="1")
    state = oc.state
    state["correct"] = "lots"  # forged non-int counter
    with pytest.raises(GameError):
        engine.submit(state=state, guess="x")


def test_validate_rejects_round_size_mismatch(engine):
    oc = engine.new_game(mode="free", user_id="1")
    state = oc.state
    state["round_size"] = 999  # no longer matches len(cards)
    with pytest.raises(GameError):
        engine.submit(state=state, guess="x")


def test_validate_rejects_overlong_answered_log(engine):
    oc = engine.new_game(mode="free", user_id="1")
    state = oc.state
    state["answered"] = [{"x": 1}] * (len(state["cards"]) + 5)  # impossible history
    with pytest.raises(GameError):
        engine.submit(state=state, guess="x")


def test_validate_rejects_missing_mode(engine):
    # mode is read via state["mode"] downstream; a state without it must fail
    # clean, not KeyError.
    oc = engine.new_game(mode="free", user_id="1")
    state = oc.state
    del state["mode"]
    with pytest.raises(GameError):
        engine.submit(state=state, guess="x")


def test_validate_rejects_null_distractors(engine):
    # distractors: null would break _card_from_dict/options() with a TypeError;
    # it must be caught as a clean GameError.
    oc = engine.new_game(mode="free", user_id="1", options={"answer_mode": "choice"})
    state = oc.state
    state["cards"][0]["distractors"] = None
    with pytest.raises(GameError):
        engine.submit(state=state, guess="x")


def test_validate_rejects_malformed_answered_entry(engine):
    # An answered entry without a str result would break result_payload /
    # _emoji_grid indexing a["result"].
    oc = engine.new_game(mode="free", user_id="1")
    state = oc.state
    state["answered"] = [{"no_result_key": True}]
    with pytest.raises(GameError):
        engine.submit(state=state, guess="x")


def test_validate_rejects_non_str_answered_fields(engine):
    # Forged answer/given (e.g. {}) flow into the recap misses list and reach
    # React as non-renderable values — must be rejected as a clean GameError.
    oc = engine.new_game(mode="free", user_id="1")
    state = oc.state
    state["answered"] = [{"result": "wrong", "answer": {}, "given": {}}]
    with pytest.raises(GameError):
        engine.submit(state=state, guess="x")


def test_validate_rejects_out_of_enum_result(engine):
    oc = engine.new_game(mode="free", user_id="1")
    state = oc.state
    state["answered"] = [{"result": "bogus", "answer": "a", "given": "b"}]
    with pytest.raises(GameError):
        engine.submit(state=state, guess="x")
