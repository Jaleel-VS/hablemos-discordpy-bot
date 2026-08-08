"""Tests for the phrasal-verb game — data, blank modes, round flow, anti-harvest.

Run: pytest activity/backend/tests  (from repo root, with the backend venv)

Mirrors test_cloze.py. Covers the two blank modes (particle / whole), the
derivative-form-accepting grader, particle-mode base reveal, daily determinism
and the replay-oracle closure, plus the committed-corpus integrity guard and
the read-only Learn deck.
"""
import copy

import pytest
from app.games.base import GameError
from app.games.phrasal import data as d
from app.games.phrasal.engine import ROUND_SIZE, PhrasalEngine

# ── committed content integrity ───────────────────────────────────────────

def test_data_loaded():
    assert d._ALL, "phrasal_verbs.json should be present and non-empty"
    assert set(d.DIFFICULTIES) >= {"beginner", "intermediate", "advanced"}


def test_every_verb_is_well_formed():
    for v in d._ALL:
        assert v["example"].count("___") == 1, f"{v['id']} needs exactly one blank"
        assert v["particle"], f"{v['id']} must have a particle"
        assert v["definitions"], f"{v['id']} must have at least one definition"
        assert v["difficulty"] in d.DIFFICULTIES
        assert isinstance(v["forms"], list) and v["forms"]
        assert len(v["distractors_particle"]) == 3
        # The particle must not also be a distractor (would be two right answers).
        assert v["particle"] not in v["distractors_particle"]


def test_enough_verbs_for_a_round():
    assert len(d._ALL) >= ROUND_SIZE


# ── config + blank mode resolution ─────────────────────────────────────────

def test_resolve_config_falls_back_on_garbage():
    assert d.resolve_config({"difficulty": "bogus"}).difficulty is None
    assert d.resolve_config(None).difficulty is None
    # Hostile unhashable values must degrade, never raise.
    assert d.resolve_config({"difficulty": ["x"]}).difficulty is None


def test_resolve_config_honors_valid_value():
    assert d.resolve_config({"difficulty": "beginner"}).difficulty == "beginner"


def test_resolve_blank_mode_defaults_to_particle():
    assert d.resolve_blank_mode(None) == "particle"
    assert d.resolve_blank_mode({"blank_mode": "nope"}) == "particle"
    assert d.resolve_blank_mode({"blank_mode": "whole"}) == "whole"


def test_pool_never_empty_for_sparse_difficulty():
    assert d.Config(difficulty="advanced").pool  # falls back to all if sparse


# ── verb selection ──────────────────────────────────────────────────────────

def test_deterministic_verbs_stable_and_distinct():
    cfg = d.default_config()
    a = d.deterministic_verbs(cfg, seed=214, count=ROUND_SIZE)
    b = d.deterministic_verbs(cfg, seed=214, count=ROUND_SIZE)
    assert [v.id for v in a] == [v.id for v in b]
    assert len({v.id for v in a}) == len(a)


def test_deterministic_verbs_differ_by_seed():
    cfg = d.default_config()
    a = d.deterministic_verbs(cfg, seed=1, count=ROUND_SIZE)
    b = d.deterministic_verbs(cfg, seed=2, count=ROUND_SIZE)
    assert [v.id for v in a] != [v.id for v in b]


def test_particle_options_include_answer_and_are_stable():
    verb = d.random_verbs(d.default_config(), count=1)[0]
    opts = verb.particle_options(seed="abc")
    assert verb.particle in opts
    assert len(opts) == 4
    assert verb.particle_options(seed="abc") == opts


def test_whole_distractors_exclude_answer():
    verb = d.random_verbs(d.default_config(), count=1)[0]
    ds = d.whole_distractors(verb.verb, seed="abc")
    assert verb.verb not in ds
    assert len(ds) == 3


# ── round flow ──────────────────────────────────────────────────────────────

@pytest.fixture
def engine():
    return PhrasalEngine()


def test_new_game_hides_answer(engine):
    oc = engine.new_game(mode="free", user_id="1", options={"answer_mode": "type"})
    assert "prompt" in oc.client_view
    assert "verbs" not in oc.client_view  # raw state (with forms) never leaks


def test_particle_mode_reveals_base_not_answer(engine):
    oc = engine.new_game(
        mode="free", user_id="1",
        options={"blank_mode": "particle", "answer_mode": "choice"},
    )
    prompt = oc.client_view["prompt"]
    assert prompt["base"]  # the base verb IS shown in particle mode
    verb = oc.state["verbs"][0]
    assert verb["particle"] in prompt["options"]
    assert len(prompt["options"]) == 4


def test_particle_mode_correct_answer_scores(engine):
    oc = engine.new_game(
        mode="free", user_id="1",
        options={"blank_mode": "particle", "answer_mode": "type"},
    )
    particle = oc.state["verbs"][0]["particle"]
    oc2 = engine.submit(state=oc.state, guess=particle)
    assert oc2.client_view["correct"] == 1
    assert oc2.client_view["last"]["result"] == "exact"


def test_whole_mode_hides_base(engine):
    oc = engine.new_game(
        mode="free", user_id="1",
        options={"blank_mode": "whole", "answer_mode": "choice"},
    )
    prompt = oc.client_view["prompt"]
    assert prompt["base"] is None  # whole mode must NOT reveal the base verb
    # Options are whole phrasal verbs, including the answer.
    assert oc.state["verbs"][0]["verb"] in prompt["options"]
    assert len(prompt["options"]) == 4


def test_whole_mode_accepts_any_derivative_form(engine):
    # In whole mode any inflected form of the phrase grades correct — a learner
    # shouldn't be marked wrong for "looked up" vs "look up".
    oc = engine.new_game(
        mode="free", user_id="1",
        options={"blank_mode": "whole", "answer_mode": "type"},
    )
    forms = oc.state["verbs"][0]["forms"]
    # Pick a form that isn't the canonical base phrase, if one exists.
    verb = oc.state["verbs"][0]["verb"]
    alt = next((f for f in forms if f != verb), forms[0])
    oc2 = engine.submit(state=oc.state, guess=alt)
    assert oc2.client_view["last"]["result"] in ("exact", "close")
    assert oc2.client_view["correct"] == 1


def test_type_mode_hides_options(engine):
    oc = engine.new_game(mode="free", user_id="1", options={"answer_mode": "type"})
    assert "options" not in oc.client_view["prompt"]


def test_wrong_answer_breaks_streak(engine):
    oc = engine.new_game(
        mode="free", user_id="1",
        options={"blank_mode": "particle", "answer_mode": "type"},
    )
    p0 = oc.state["verbs"][0]["particle"]
    oc = engine.submit(state=oc.state, guess=p0)
    assert oc.client_view["streak"] == 1
    oc = engine.submit(state=oc.state, guess="zzz-not-a-particle")
    assert oc.client_view["streak"] == 0
    assert oc.client_view["last"]["result"] == "wrong"


def test_round_ends_after_round_size(engine):
    oc = engine.new_game(
        mode="free", user_id="1",
        options={"blank_mode": "particle", "answer_mode": "choice"},
    )
    state = oc.state
    for _ in range(ROUND_SIZE):
        assert not engine.is_over(state)
        state = engine.submit(state=state, guess=state["verbs"][state["seq"]]["particle"]).state
    assert engine.is_over(state)
    result = engine.result_payload(state)
    assert result["score"] == f"{ROUND_SIZE}/{ROUND_SIZE}"
    assert result["won"] is True


def test_finish_ends_freeplay_early(engine):
    oc = engine.new_game(mode="free", user_id="1", options={"answer_mode": "type"})
    oc2 = engine.submit(state=oc.state, guess="", finish=True)
    assert engine.is_over(oc2.state)


def test_daily_early_finish_rejected(engine):
    oc = engine.new_game(mode="daily", user_id="1", options={})
    with pytest.raises(GameError):
        engine.submit(state=oc.state, guess="", finish=True)


def test_daily_expires_next_day(engine):
    oc = engine.new_game(mode="daily", user_id="1", options={})
    oc.state["date"] = "2020-01-01"
    with pytest.raises(GameError):
        engine.submit(state=oc.state, guess="whatever")


def test_empty_guess_rejected(engine):
    oc = engine.new_game(mode="free", user_id="1", options={"answer_mode": "type"})
    with pytest.raises(GameError):
        engine.submit(state=oc.state, guess="   ")


def test_submit_after_over_rejected(engine):
    oc = engine.new_game(mode="free", user_id="1")
    over = engine.submit(state=oc.state, guess="", finish=True).state
    with pytest.raises(GameError):
        engine.submit(state=over, guess="x")


def test_hostile_state_rejected(engine):
    with pytest.raises(GameError):
        engine.submit(state={"game": "phrasal"}, guess="x")  # missing verbs/seq
    with pytest.raises(GameError):
        engine.submit(state={"game": "wrong"}, guess="x")


# ── daily determinism + anti-harvest ────────────────────────────────────────

def test_daily_is_deterministic_across_users(engine):
    a = engine.new_game(mode="daily", user_id="1", options={})
    b = engine.new_game(mode="daily", user_id="2", options={})
    assert [v["id"] for v in a.state["verbs"]] == [v["id"] for v in b.state["verbs"]]


def test_daily_withholds_all_feedback(engine):
    oc = engine.new_game(mode="daily", user_id="1", options={"answer_mode": "choice"})
    particle = oc.state["verbs"][0]["particle"]
    oc2 = engine.submit(state=oc.state, guess=particle)
    view = oc2.client_view
    assert view["last"] is None
    assert view["correct"] is None
    assert view["streak"] is None
    assert view["best_streak"] is None
    assert view["answered_count"] == 1
    assert oc2.state["correct"] == 1  # internal state still tracks it


def test_daily_replay_oracle_is_closed(engine):
    # Replaying the same daily token against each option must yield identical
    # client views — otherwise a varying field is itself the oracle.
    oc = engine.new_game(mode="daily", user_id="1", options={"answer_mode": "choice"})
    options = oc.client_view["prompt"]["options"]
    assert len(options) == 4
    views = []
    for opt in options:
        outcome = engine.submit(state=copy.deepcopy(oc.state), guess=opt)
        views.append(outcome.client_view)
    assert all(v == views[0] for v in views), "daily view must not vary by guess"


def test_freeplay_shows_live_counters(engine):
    oc = engine.new_game(
        mode="free", user_id="1",
        options={"blank_mode": "particle", "answer_mode": "choice"},
    )
    oc2 = engine.submit(state=oc.state, guess=oc.state["verbs"][0]["particle"])
    assert oc2.client_view["correct"] == 1


def test_recap_exposes_misses(engine):
    oc = engine.new_game(mode="daily", user_id="1", options={"answer_mode": "type"})
    state = oc.state
    for _ in range(ROUND_SIZE):
        if engine.is_over(state):
            break
        state = engine.submit(state=state, guess="wrong-xyz").state
    result = engine.result_payload(state)
    assert len(result["misses"]) == ROUND_SIZE
    assert all("answer" in m for m in result["misses"])


# ── Learn deck (read-only, not part of the engine) ──────────────────────────

def test_learn_deck_is_answer_safe_and_unblanked():
    deck = d.learn_deck()
    assert deck
    for entry in deck[:20]:
        # Learn shows the verb in a full sentence (no blank) and all senses.
        assert "___" not in entry["example"]
        assert entry["verb"]
        assert entry["definitions"]
        # No answer-material leakage beyond what Learn intentionally shows
        # (forms/distractors are exercise-only).
        assert "forms" not in entry
        assert "distractors_particle" not in entry


def test_learn_deck_filters_by_difficulty():
    beginner = d.learn_deck("beginner")
    assert all(e["difficulty"] == "beginner" for e in beginner)
    # An invalid difficulty returns the full deck, not empty.
    assert len(d.learn_deck("bogus")) == len(d.learn_deck())
