"""Tests for the cloze (fill-in-the-blank) game — data, config, round flow.

Run: pytest activity/backend/tests  (from repo root, with the backend venv)

Mirrors the shape of test_conjugation.py: it exercises grading (reused from the
conjugation normalizer), config resolution/normalization, the round flow,
daily determinism + answer-withholding, and hostile-state guards. It also
guards the committed content JSON so a bad regeneration can't silently ship.
"""
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


def test_daily_withholds_answer_in_feedback(engine):
    oc = engine.new_game(mode="daily", user_id="1", options={"answer_mode": "choice"})
    answer = oc.state["cards"][0]["answer"]
    oc2 = engine.submit(state=oc.state, guess=answer)
    last = oc2.client_view["last"]
    assert last is not None
    assert "answer" not in last          # withheld mid-run in daily
    assert last["result"] == "exact"     # but the flag is present


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
