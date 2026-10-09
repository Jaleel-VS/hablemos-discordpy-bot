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
    # In choice mode a wrong answer advances immediately (reveal-then-continue
    # path); streak resets on the answer, not on the continue.
    oc = engine.new_game(mode="free", user_id="1", options={"answer_mode": "choice"})
    a0 = oc.state["cards"][0]["answer"]
    # First card: correct answer → streak 1.
    oc = engine.submit(state=oc.state, guess=a0)
    assert oc.client_view["streak"] == 1
    # Wrong answer: sets awaiting_continue and resets streak.
    oc = engine.submit(state=oc.state, guess="definitely-wrong-xyz")
    assert oc.client_view["streak"] == 0
    assert oc.client_view["last"]["result"] == "wrong"
    assert oc.client_view["awaiting_continue"] is True


def test_accent_only_miss_is_close(engine):
    # Find a card whose answer carries an accent so we can test the CLOSE tier.
    # Use choice mode so the CLOSE answer advances without triggering retry.
    oc = engine.new_game(mode="free", user_id="1", options={"answer_mode": "choice"})
    # Force a known accented answer into the current card for a deterministic test.
    accented = "caf\u00e9"
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


# ── new C1/C2/C5 behavior tests ────────────────────────────────────────────

# ── C1 freeplay miss mechanics ──────────────────────────────────────────────

def test_type_mode_wrong_sets_awaiting_retry(engine):
    # After a wrong answer in type mode freeplay, the same card stays and the
    # client must retype (awaiting_retry=True). Score and seq do NOT change.
    oc = engine.new_game(mode="free", user_id="1", options={"answer_mode": "type"})
    seq_before = oc.state["seq"]
    oc2 = engine.submit(state=oc.state, guess="wrong-xyz")
    assert oc2.client_view["awaiting_retry"] is True
    assert oc2.client_view["seq"] == seq_before    # same card
    assert oc2.client_view["correct"] == 0         # no score yet
    assert oc2.client_view["answered_count"] == 1  # logged


def test_type_mode_retry_on_correct_advances(engine):
    oc = engine.new_game(mode="free", user_id="1", options={"answer_mode": "type"})
    seq_before = oc.state["seq"]
    answer = oc.state["cards"][0]["answer"]
    oc = engine.submit(state=oc.state, guess="wrong-xyz")
    assert oc.client_view["awaiting_retry"] is True
    # Retry with the correct answer: should advance.
    oc2 = engine.submit(state=oc.state, guess=answer, action="retry")
    assert oc2.client_view["awaiting_retry"] is False
    assert oc2.client_view["seq"] == seq_before + 1


def test_type_mode_retry_forced_advance_after_two_failures(engine):
    # After 2 failed retries the engine forces advance regardless of the answer.
    oc = engine.new_game(mode="free", user_id="1", options={"answer_mode": "type"})
    oc = engine.submit(state=oc.state, guess="wrong-xyz")  # first wrong -> awaiting_retry
    assert oc.client_view["awaiting_retry"] is True
    oc = engine.submit(state=oc.state, guess="still-wrong", action="retry")  # retry 1 fail
    assert oc.client_view["awaiting_retry"] is True
    oc = engine.submit(state=oc.state, guess="still-wrong-2", action="retry")  # retry 2 -> force
    # After 2 failed retries, forced advance.
    assert oc.client_view["awaiting_retry"] is False


def test_type_mode_skip_advances_without_retry(engine):
    oc = engine.new_game(mode="free", user_id="1", options={"answer_mode": "type"})
    seq_before = oc.state["seq"]
    oc2 = engine.submit(state=oc.state, guess="", action="skip")
    assert oc2.client_view["seq"] == seq_before + 1
    assert oc2.client_view["awaiting_retry"] is False


def test_type_mode_skip_rejected_while_awaiting_retry(engine):
    oc = engine.new_game(mode="free", user_id="1", options={"answer_mode": "type"})
    oc = engine.submit(state=oc.state, guess="wrong-xyz")
    assert oc.client_view["awaiting_retry"] is True
    with pytest.raises(GameError):
        engine.submit(state=oc.state, guess="", action="skip")


def test_freeplay_last_has_sentence_and_context_on_wrong(engine):
    # Freeplay miss: last must carry the completed sentence + context.
    oc = engine.new_game(mode="free", user_id="1", options={"answer_mode": "type"})
    card = oc.state["cards"][0]
    oc2 = engine.submit(state=oc.state, guess="wrong-xyz")
    last = oc2.client_view["last"]
    assert last is not None
    assert "sentence" in last
    assert "context" in last
    # Completed sentence should contain the answer word.
    assert card["answer"] in last["sentence"]
    assert "___" not in last["sentence"]


def test_choice_mode_wrong_sets_awaiting_continue(engine):
    oc = engine.new_game(mode="free", user_id="1", options={"answer_mode": "choice"})
    seq_before = oc.state["seq"]
    oc2 = engine.submit(state=oc.state, guess="wrong-xyz")
    assert oc2.client_view["awaiting_continue"] is True
    assert oc2.client_view["seq"] == seq_before    # same card
    assert oc2.client_view["correct"] == 0


def test_choice_mode_continue_advances(engine):
    oc = engine.new_game(mode="free", user_id="1", options={"answer_mode": "choice"})
    seq_before = oc.state["seq"]
    oc = engine.submit(state=oc.state, guess="wrong-xyz")
    assert oc.client_view["awaiting_continue"] is True
    oc2 = engine.submit(state=oc.state, guess="", action="continue")
    assert oc2.client_view["awaiting_continue"] is False
    assert oc2.client_view["seq"] == seq_before + 1


def test_daily_rejects_retry_skip_continue(engine):
    oc = engine.new_game(mode="daily", user_id="1", options={"answer_mode": "type"})
    for action in ("retry", "skip", "continue"):
        with pytest.raises(GameError):
            engine.submit(state=copy.deepcopy(oc.state), guess="x", action=action)


# ── C2 result review_ids + misses sentence/context ──────────────────────────

def test_result_has_review_ids_for_wrong_cards(engine):
    oc = engine.new_game(mode="daily", user_id="1", options={"answer_mode": "type"})
    state = oc.state
    for _ in range(ROUND_SIZE):
        if engine.is_over(state):
            break
        state = engine.submit(state=state, guess="wrong-xyz").state
    result = engine.result_payload(state)
    assert "review_ids" in result
    # All wrong answers → review_ids should have up to 10 unique ids.
    assert len(result["review_ids"]) <= 10
    assert len(result["review_ids"]) == len(set(result["review_ids"]))  # deduped
    # Each review_id must match a miss entry.
    miss_ids = {m["id"] for m in result["misses"]}
    assert set(result["review_ids"]).issubset(miss_ids)


def test_result_misses_have_sentence_and_context(engine):
    # The recap miss rows must include the completed sentence + context so the
    # learner sees the word in context (daily and freeplay both get this).
    oc = engine.new_game(mode="daily", user_id="1", options={"answer_mode": "type"})
    state = oc.state
    for _ in range(ROUND_SIZE):
        if engine.is_over(state):
            break
        state = engine.submit(state=state, guess="wrong-xyz").state
    result = engine.result_payload(state)
    for miss in result["misses"]:
        assert "sentence" in miss, f"miss {miss['id']} missing sentence"
        assert "context" in miss, f"miss {miss['id']} missing context"
        # Completed sentence must not have the blank anymore.
        assert "___" not in miss["sentence"]
        assert miss["answer"] in miss["sentence"]


def test_id_not_in_in_play_prompt(engine):
    # Card id must not appear in the prompt during play (security invariant:
    # an in-play id lets a client correlate sealed state with static card data).
    for mode in ("free", "daily"):
        oc = engine.new_game(mode=mode, user_id="1", options={"answer_mode": "type"})
        assert "id" not in oc.client_view.get("prompt", {})
    oc = engine.new_game(mode="free", user_id="1", options={"answer_mode": "choice"})
    assert "id" not in oc.client_view.get("prompt", {})


# ── options.ids review round ─────────────────────────────────────────────────

def test_options_ids_freeplay_round_uses_specified_cards(engine):
    # Using options.ids in freeplay should draw from the given ids (minus any
    # that are in today's daily set).
    cfg = d.default_config()
    # Use non-daily cards by computing today's daily ids and picking outside them.
    from app.games.cloze.data import _today_daily_ids
    daily_ids = _today_daily_ids()
    available = [c["id"] for c in d._BY_TARGET[cfg.target] if c["id"] not in daily_ids]
    pick_ids = available[:3]
    oc = engine.new_game(mode="free", user_id="1", options={
        "target": cfg.target, "answer_mode": "type", "ids": pick_ids,
    })
    actual_ids = [c["id"] for c in oc.state["cards"]]
    assert all(i in pick_ids for i in actual_ids)


def test_options_ids_drops_daily_ids(engine):
    from app.games.cloze.data import (
        Config,
        _today_daily_ids,
        random_cards_by_ids,
    )
    daily_ids = list(_today_daily_ids())
    # Passing only today's daily ids must produce None (all dropped), so
    # random_cards_by_ids returns None and the engine falls back to a random round.
    result = random_cards_by_ids(daily_ids, target="es", count=10, config=Config("es", None))
    assert result is None, "All daily ids should be dropped, returning None"
    # Engine falls back gracefully — a valid round is started.
    oc = engine.new_game(mode="free", user_id="1", options={
        "target": "es", "answer_mode": "choice", "ids": daily_ids,
    })
    assert len(oc.state["cards"]) == ROUND_SIZE



# ── C5 bucket data invariants ────────────────────────────────────────────────

def test_each_bucket_has_at_least_40_cards():
    """Data contract: every (target, difficulty) bucket must have >= 40 cards."""
    for target in d.TARGETS:
        for diff in d.DIFFICULTIES:
            bucket = [c for c in d._ALL_CARDS
                      if c.get("target") == target and c.get("difficulty") == diff]
            assert len(bucket) >= 40, (
                f"Bucket {target}/{diff} has only {len(bucket)} cards (need >= 40)"
            )


def test_empty_bucket_raises_game_error(engine):
    # Engine must raise GameError (not silently mix) when a requested difficulty
    # bucket is empty. We test via data.Config.pool directly.
    from app.games.base import GameError as GE
    from app.games.cloze.data import Config
    # Construct a config for a non-existent target/difficulty combo.
    bad_cfg = Config(target="es", difficulty="__nonexistent__")
    with pytest.raises(GE):
        _ = bad_cfg.pool


# ── sealed state size ────────────────────────────────────────────────────────

def _heaviest_ids(target: str) -> list[str]:
    """The ten largest cards in a deck — what a hostile `options.ids` would pick."""
    import json

    cards = sorted(
        (c for c in d._raw["cards"] if c["target"] == target),
        key=lambda c: -len(json.dumps(c, ensure_ascii=False)),
    )
    return [c["id"] for c in cards[:ROUND_SIZE]]


@pytest.mark.parametrize("target", ["en", "es"])
def test_sealed_state_fits_cap_for_heaviest_cards_and_longest_guesses(engine, target):
    """The real token (Fernet-sealed, with routes' identity fields) must stay
    under routes._MAX_SEALED at every step, for the heaviest cards a client can
    request via options.ids and the longest guesses the request allows."""
    from app.games.routes import _MAX_GUESS, _MAX_SEALED
    from app.games.sealed_state import seal

    state = engine.new_game(
        mode="free", user_id="1",
        options={"target": target, "answer_mode": "type", "ids": _heaviest_ids(target)},
    ).state
    overhead = {"_uid": 2**63 - 1, "_uname": "A" * 32, "_sid": "a" * 36, "_gid": 2**63 - 1}
    worst = 0
    while not engine.is_over(state):
        state = engine.submit(state=state, guess="x" * _MAX_GUESS).state
        while state.get("awaiting_retry"):
            state = engine.submit(state=state, guess="y" * _MAX_GUESS, action="retry").state
        worst = max(worst, len(seal("s" * 32, {**state, **overhead})))
    assert worst < _MAX_SEALED, f"sealed state reached {worst} bytes (cap {_MAX_SEALED})"


def test_skip_rejected_while_choice_miss_awaits_continue(engine):
    """Skipping a pending choice-mode miss would log the card twice and desync
    answered vs cards until the state is rejected for good."""
    oc = engine.new_game(mode="free", user_id="1", options={"answer_mode": "choice"})
    state = oc.state
    wrong = next(o for o in oc.client_view["prompt"]["options"] if o != state["cards"][0]["answer"])
    state = engine.submit(state=state, guess=wrong).state
    assert state["awaiting_continue"] is True
    with pytest.raises(GameError):
        engine.submit(state=copy.deepcopy(state), guess="", action="skip")
    assert len(state["answered"]) == 1


def test_retry_feedback_names_the_answer(engine):
    """After a failed retype the reveal must still show the word to copy, and a
    successful retype acknowledges the word (not an empty string)."""
    state = engine.new_game(mode="free", user_id="1", options={"answer_mode": "type"}).state
    answer = state["cards"][0]["answer"]
    state = engine.submit(state=state, guess="zzzz").state
    failed = engine.submit(state=copy.deepcopy(state), guess="qqqq", action="retry")
    assert failed.state["awaiting_retry"] is True
    assert failed.client_view["last"]["answer"] == answer
    assert answer in failed.client_view["last"]["sentence"]
    ok = engine.submit(state=copy.deepcopy(state), guess=answer, action="retry")
    assert ok.client_view["last"]["retry"] is True
    assert ok.client_view["last"]["answer"] == answer


def test_unknown_action_rejected(engine):
    state = engine.new_game(mode="free", user_id="1", options={}).state
    with pytest.raises(GameError):
        engine.submit(state=state, guess="x", action="teleport")


def test_daily_result_offers_no_review_round(engine):
    """Today's daily cards are excluded from review rounds, so the daily recap
    must not offer a 'practise these' that would start an unrelated round."""
    state = engine.new_game(mode="daily", user_id="1", options={}).state
    while not engine.is_over(state):
        state = engine.submit(state=state, guess="zzzz").state
    result = engine.result_payload(state)
    assert result["misses"], "an all-wrong daily must still list its misses"
    assert result["review_ids"] == []
