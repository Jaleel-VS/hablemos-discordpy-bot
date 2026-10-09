"""Behaviour tests for new engine features in the phrasal-verb game.

Covers:
- P0: slim state seal-size invariants (3000 fresh games + completed 10-item round)
- P0: id stripped from in-play prompt
- P0: verb rebuilt from id (unknown id → GameError)
- P0: daily rejects skip/retry/continue
- P2: type-mode awaiting_retry loop, forced advance after max retries
- P2: choice-mode awaiting_continue + continue action
- P3: review_ids in result (wrong+close, capped 10, daily ids excluded)
- P3: options.ids freeplay start (dedup, cap, validation, daily drop, fallback)
"""
from __future__ import annotations

import copy

import pytest
from app.games.base import GameError
from app.games.phrasal import data as d
from app.games.phrasal.engine import (
    ROUND_SIZE,
    PhrasalEngine,
    _today_daily_ids,
)
from app.games.sealed_state import seal

_SECRET = "test-secret-for-size"


# ── helpers ───────────────────────────────────────────────────────────────────


@pytest.fixture
def engine():
    return PhrasalEngine()


def _start(engine, *, mode="free", answer_mode="type", blank_mode="particle", options=None):
    if options is None:
        options = {"answer_mode": answer_mode, "blank_mode": blank_mode}
    return engine.new_game(mode=mode, user_id="1", options=options)


def _answer_all_wrong(engine, oc):
    """Submit wrong guesses to every item in the round (freeplay choice mode)."""
    state = oc.state
    while state["status"] == "playing":
        if state.get("awaiting_continue"):
            # advance past awaiting_continue
            oc = engine.submit(state=state, guess="", action="continue")
            state = oc.state
            continue
        wrong_guess = "definitely_wrong_xyz"
        oc = engine.submit(state=state, guess=wrong_guess)
        state = oc.state
    return oc


# ── P0: sealed-state size ─────────────────────────────────────────────────────


def test_seal_size_3000_fresh_games_all_under_7000():
    """No fresh-game sealed state (+ route-injected fields) exceeds 7000 bytes."""
    eng = PhrasalEngine()
    # Simulate what routes.py adds before sealing.
    route_overhead: dict = {
        "_uid": 123456789012345678,
        "_uname": "a" * 32,
        "_sid": "a" * 36,
        "_gid": 987654321098765432,
    }
    max_size = 0
    for _ in range(3000):
        oc = eng.new_game(mode="free", user_id="1", options={"answer_mode": "type", "blank_mode": "whole"})
        state = {**oc.state, **route_overhead}
        token = seal(_SECRET, state)
        max_size = max(max_size, len(token))

    assert max_size < 7000, f"max sealed size {max_size} >= 7000"


def test_seal_size_completed_round_with_misses_under_7000():
    """A fully answered 10-item round with misses + retry fields seals under 7000."""
    eng = PhrasalEngine()
    route_overhead = {
        "_uid": 123456789012345678,
        "_uname": "a" * 32,
        "_sid": "a" * 36,
        "_gid": 987654321098765432,
    }
    oc = eng.new_game(mode="free", user_id="1", options={"answer_mode": "choice", "blank_mode": "whole"})
    oc = _answer_all_wrong(eng, oc)
    state = {**oc.state, **route_overhead}
    token = seal(_SECRET, state)
    assert len(token) < 7000, f"completed-round sealed size {len(token)} >= 7000"


# ── P0: id not in prompt ──────────────────────────────────────────────────────


def test_prompt_does_not_expose_id(engine):
    oc = _start(engine)
    prompt = oc.client_view.get("prompt", {})
    assert "id" not in prompt, "prompt must not contain id"


# ── P0: unknown verb id → GameError ──────────────────────────────────────────


def test_hostile_unknown_verb_id_raises(engine):
    oc = _start(engine)
    bad_state = copy.deepcopy(oc.state)
    bad_state["verb_ids"][0] = "pv-DOES-NOT-EXIST"
    with pytest.raises(GameError):
        engine.submit(state=bad_state, guess="up")


# ── P0: daily rejects skip/retry/continue ────────────────────────────────────


@pytest.mark.parametrize("mode", ["daily", "free"])
def test_skip_is_not_an_action(engine, mode):
    """Phrasal has no skip; it must be rejected, never graded as an answer."""
    oc = engine.new_game(mode=mode, user_id="1", options={})
    with pytest.raises(GameError):
        engine.submit(state=oc.state, guess="up", action="skip")


def test_daily_rejects_retry(engine):
    oc = engine.new_game(mode="daily", user_id="1", options={})
    with pytest.raises(GameError, match="Acción no disponible"):
        engine.submit(state=oc.state, guess="up", action="retry")


def test_daily_rejects_continue(engine):
    oc = engine.new_game(mode="daily", user_id="1", options={})
    with pytest.raises(GameError, match="Acción no disponible"):
        engine.submit(state=oc.state, guess="up", action="continue")


# ── P2: type-mode awaiting_retry ─────────────────────────────────────────────


def test_type_mode_wrong_enters_awaiting_retry(engine):
    oc = _start(engine, answer_mode="type")
    state = oc.state
    seq = state["seq"]

    oc2 = engine.submit(state=copy.deepcopy(state), guess="definitely_wrong")
    assert oc2.client_view["awaiting_retry"] is True
    # Score did not change.
    assert oc2.state["correct"] == 0
    assert oc2.state["seq"] == seq  # did not advance


def test_type_mode_correct_retry_advances(engine):
    oc = _start(engine, answer_mode="type")
    state = oc.state
    seq = state["seq"]
    verb = d.verb_by_id(state["verb_ids"][seq])
    correct_answer = verb.accepted_forms("particle")[0]

    # First: wrong answer → awaiting_retry
    oc2 = engine.submit(state=copy.deepcopy(state), guess="wrong_answer")
    assert oc2.state.get("awaiting_retry") is True

    # Retry with correct answer → advances
    oc3 = engine.submit(state=copy.deepcopy(oc2.state), guess=correct_answer, action="retry")
    assert oc3.state["seq"] == seq + 1
    assert oc3.state.get("awaiting_retry") is False
    # Score did NOT change (retry doesn't count).
    assert oc3.state["correct"] == 0


def test_type_mode_forced_advance_after_max_retries(engine):
    oc = _start(engine, answer_mode="type")
    state = oc.state
    seq = state["seq"]

    # Miss → awaiting_retry
    oc2 = engine.submit(state=copy.deepcopy(state), guess="wrong")
    # Two failed retries → forced advance
    oc3 = engine.submit(state=copy.deepcopy(oc2.state), guess="wrong", action="retry")
    assert oc3.state.get("awaiting_retry") is True  # still, 1st failed retry
    oc4 = engine.submit(state=copy.deepcopy(oc3.state), guess="wrong", action="retry")
    # After 2 failed retries → forced advance
    assert oc4.state["seq"] == seq + 1
    assert oc4.state.get("awaiting_retry") is False


def test_type_mode_retry_no_score_change(engine):
    oc = _start(engine, answer_mode="type")
    state = oc.state
    seq = state["seq"]
    verb = d.verb_by_id(state["verb_ids"][seq])
    correct = verb.accepted_forms("particle")[0]

    # Wrong → retry → correct: score should still be 0 for this item.
    oc2 = engine.submit(state=copy.deepcopy(state), guess="wrong")
    oc3 = engine.submit(state=copy.deepcopy(oc2.state), guess=correct, action="retry")
    assert oc3.state["correct"] == 0


# ── P2: choice-mode awaiting_continue ────────────────────────────────────────


def test_choice_mode_wrong_enters_awaiting_continue(engine):
    oc = _start(engine, answer_mode="choice")
    state = oc.state
    seq = state["seq"]

    oc2 = engine.submit(state=copy.deepcopy(state), guess="definitely_wrong_xyz")
    assert oc2.client_view["awaiting_continue"] is True
    assert oc2.state["seq"] == seq  # did not advance


def test_choice_mode_continue_advances(engine):
    oc = _start(engine, answer_mode="choice")
    state = oc.state
    seq = state["seq"]

    oc2 = engine.submit(state=copy.deepcopy(state), guess="definitely_wrong_xyz")
    assert oc2.state.get("awaiting_continue") is True

    oc3 = engine.submit(state=copy.deepcopy(oc2.state), guess="", action="continue")
    assert oc3.state["seq"] == seq + 1
    assert oc3.state.get("awaiting_continue") is False


def test_choice_mode_answer_rejected_while_awaiting_continue(engine):
    oc = _start(engine, answer_mode="choice")
    state = oc.state
    verb = d.verb_by_id(state["verb_ids"][state["seq"]])
    correct = verb.accepted_forms("particle")[0]

    oc2 = engine.submit(state=copy.deepcopy(state), guess="definitely_wrong_xyz")
    with pytest.raises(GameError, match="Confirma"):
        engine.submit(state=copy.deepcopy(oc2.state), guess=correct, action="answer")


# ── P2: last carries gloss_es + sentence ─────────────────────────────────────


def test_freeplay_miss_last_has_gloss_and_sentence(engine):
    oc = _start(engine, answer_mode="choice")
    state = oc.state
    seq = state["seq"]
    verb = d.verb_by_id(state["verb_ids"][seq])

    oc2 = engine.submit(state=copy.deepcopy(state), guess="definitely_wrong_xyz")
    last = oc2.client_view.get("last")
    assert last is not None
    # The reveal teaches *this* verb: its own gloss and the example with the
    # blank filled by its own answer.
    assert last["gloss_es"] == verb.gloss_es
    assert "___" not in last["sentence"]
    assert last["answer"] in last["sentence"]


# ── P3: review_ids in result ──────────────────────────────────────────────────


def test_review_ids_in_result_contains_missed_ids(engine):
    oc = engine.new_game(mode="free", user_id="1", options={"answer_mode": "choice", "blank_mode": "particle"})
    oc = _answer_all_wrong(engine, oc)
    result = oc.client_view["result"]
    assert "review_ids" in result
    assert len(result["review_ids"]) > 0
    # All must be valid deck ids.
    deck_ids = {v["id"] for v in d._ALL}
    for vid in result["review_ids"]:
        assert vid in deck_ids


def test_review_ids_capped_at_10(engine):
    oc = engine.new_game(mode="free", user_id="1", options={"answer_mode": "choice", "blank_mode": "particle"})
    oc = _answer_all_wrong(engine, oc)
    result = oc.client_view["result"]
    assert len(result["review_ids"]) <= 10


def test_review_ids_excludes_todays_daily_ids(engine):
    daily_ids = _today_daily_ids()
    oc = engine.new_game(mode="free", user_id="1", options={"answer_mode": "choice"})
    oc = _answer_all_wrong(engine, oc)
    result = oc.client_view["result"]
    for vid in result["review_ids"]:
        assert vid not in daily_ids, f"daily id {vid!r} leaked into review_ids"


def test_review_ids_deduplicated(engine):
    oc = engine.new_game(mode="free", user_id="1", options={"answer_mode": "choice"})
    oc = _answer_all_wrong(engine, oc)
    result = oc.client_view["result"]
    assert len(result["review_ids"]) == len(set(result["review_ids"]))


# ── P3: options.ids freeplay start ───────────────────────────────────────────


def test_options_ids_starts_round_with_requested_verbs(engine):
    # Pick some ids that are NOT today's daily ids.
    daily_ids = _today_daily_ids()
    non_daily = [v["id"] for v in d._ALL if v["id"] not in daily_ids]
    ids = non_daily[:5]
    oc = engine.new_game(mode="free", user_id="1", options={"answer_mode": "choice", "ids": ids})
    assert set(oc.state["verb_ids"]) == set(ids)


def test_options_ids_deduped_and_capped_at_10(engine):
    daily_ids = _today_daily_ids()
    non_daily = [v["id"] for v in d._ALL if v["id"] not in daily_ids]
    # Pass 15 ids (5 duplicates).
    ids = non_daily[:10] + non_daily[:5]
    oc = engine.new_game(mode="free", user_id="1", options={"answer_mode": "choice", "ids": ids})
    assert len(oc.state["verb_ids"]) <= 10
    assert len(set(oc.state["verb_ids"])) == len(oc.state["verb_ids"])


def test_options_ids_drops_today_daily_ids(engine):
    daily_ids = list(_today_daily_ids())
    assert len(daily_ids) == ROUND_SIZE
    non_daily = [v["id"] for v in d._ALL if v["id"] not in daily_ids]
    # Mix daily + non-daily ids.
    ids = daily_ids[:3] + non_daily[:5]
    oc = engine.new_game(mode="free", user_id="1", options={"answer_mode": "choice", "ids": ids})
    for vid in oc.state["verb_ids"]:
        assert vid not in daily_ids, f"daily id {vid!r} leaked into options.ids game"


def test_options_ids_falls_back_to_random_if_all_invalid(engine):
    # All ids are unknown → falls back to random round.
    oc = engine.new_game(mode="free", user_id="1", options={"answer_mode": "choice", "ids": ["pv-FAKE-1", "pv-FAKE-2"]})
    assert oc.state["round_size"] == ROUND_SIZE  # normal random round


def test_options_ids_falls_back_to_random_if_only_daily(engine):
    daily_ids = list(_today_daily_ids())
    oc = engine.new_game(mode="free", user_id="1", options={"answer_mode": "choice", "ids": daily_ids})
    # All passed ids are daily ids → should fall back to random round.
    assert oc.state["round_size"] == ROUND_SIZE


# ── data: verb_by_id ──────────────────────────────────────────────────────────


def test_verb_by_id_returns_correct_verb():
    first = d._ALL[0]
    verb = d.verb_by_id(first["id"])
    assert verb is not None
    assert verb.id == first["id"]
    assert verb.verb == first["verb"]


def test_verb_by_id_returns_none_for_unknown():
    assert d.verb_by_id("pv-DOES-NOT-EXIST-AT-ALL") is None


def test_verbs_by_ids_order_preserved():
    non_daily = [v["id"] for v in d._ALL if "id" in v][:5]
    verbs = d.verbs_by_ids(non_daily)
    assert [v.id for v in verbs] == non_daily


def test_verbs_by_ids_drops_unknown():
    ids = [d._ALL[0]["id"], "pv-BAD", d._ALL[1]["id"]]
    verbs = d.verbs_by_ids(ids)
    assert len(verbs) == 2


# ── particle mode reads as real English ───────────────────────────────────────


def _verb_with_inflected_span() -> d.Verb:
    """A deck verb whose example blank is an inflected span ending in the particle."""
    for vid in d._ID_INDEX:
        v = d.verb_by_id(vid)
        if v.example_answer.lower() != v.verb.lower() and v.example_answer.lower().endswith(" " + v.particle):
            return v
    raise AssertionError("deck has no inflected particle span")


def test_particle_prompt_writes_inflected_verb_and_blanks_only_particle():
    verb = _verb_with_inflected_span()
    inflected = verb.example_answer[: -len(verb.particle)].rstrip()
    prompt = verb.prompt(blank_mode="particle", options=None)
    assert f"{inflected} ___" in prompt["example"]
    assert prompt["base_inline"] is True
    # Filling the remaining blank with the particle restores the original sentence.
    assert prompt["example"].replace("___", verb.particle, 1) == verb.example.replace("___", verb.example_answer, 1)


def test_particle_mode_miss_reveal_uses_full_span(engine):
    """Missing a particle reveals the sentence with the whole span, never 'about over'."""
    verb = _verb_with_inflected_span()
    oc = _start(engine, answer_mode="type", blank_mode="particle")
    state = copy.deepcopy(oc.state)
    state["verb_ids"][state["seq"]] = verb.id
    last = engine.submit(state=state, guess="definitely_wrong").client_view["last"]
    assert last["answer"] == verb.particle
    assert last["span"] == verb.example_answer
    assert last["sentence"] == verb.example.replace("___", verb.example_answer, 1)
