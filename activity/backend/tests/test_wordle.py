"""Tests for the Spanish Wordle engine — normalization, scoring, game flow.

Run: pytest activity/backend/tests  (from repo root, with the backend venv)
"""
from datetime import date

import pytest

from app.games.base import GameError
from app.games.wordle import daily as daily_mod
from app.games.wordle.engine import WordleEngine
from app.games.wordle.normalize import is_valid_shape, letters, normalize
from app.games.wordle.scorer import Tile, emoji_row, score
from app.games.wordle.words import ANSWERS


# ── normalization ─────────────────────────────────────────────────────────

def test_accents_stripped():
    assert normalize("ACCIÓN") == "accion"
    assert normalize("árbol") == "arbol"
    assert normalize("pingüino") == "pinguino"


def test_ñ_preserved_as_single_letter():
    n = normalize("PEÑAS")
    assert n == "peñas"
    assert letters(n) == ["p", "e", "ñ", "a", "s"]
    assert len(letters(n)) == 5


def test_ñ_not_destroyed_by_accent_strip():
    # The NFD trap: ñ decomposes to n + combining tilde. Must survive.
    assert normalize("ñandu") == "ñandu"
    assert "n" != normalize("ñ")  # ñ must NOT collapse to n
    assert normalize("ñ") == "ñ"


def test_valid_shape():
    assert is_valid_shape("gatos")
    assert is_valid_shape("peñas")  # ñ counts as one
    assert not is_valid_shape("gato")     # 4 letters
    assert not is_valid_shape("gatos1")   # digit
    assert not is_valid_shape("gat os")   # space


# ── scorer: the duplicate-letter cases that break naive implementations ─────

def _tiles(guess, answer):
    return [t.value for t in score(guess, answer)]


def test_all_green():
    assert _tiles("gatos", "gatos") == ["green"] * 5


def test_all_gray():
    assert _tiles("plumr", "gatos") == [
        # p,l,u,m,r none in "gatos"
        "gray", "gray", "gray", "gray", "gray",
    ]


def test_yellow_reposition():
    # "aloja" vs "hojas": letters present but positions differ
    result = _tiles("oitas", "gatos")
    # o(0) in gatos? gatos has o at idx3 -> yellow; i absent; t at idx2 in
    # gatos? gatos[2]=t -> green; a at idx3, gatos[3]=o no, a present at
    # idx1 -> yellow; s at idx4 green
    assert result == ["yellow", "gray", "green", "yellow", "green"]


def test_duplicate_letter_guess_one_in_answer():
    # answer has ONE 'a'; guess has TWO. Only one should be colored.
    # answer "casta" actually has two a's... use "pato" style with 5 letters.
    # answer "salsa" has two a's and two s's.
    # Use answer with a single 'e': "peras" (p,e,r,a,s) - one e.
    # guess "elefe" not valid shape concerns aside, test scorer directly.
    result = _tiles("eexxx", "peras")  # two e's guessed, answer has one e (idx1)
    # first e (idx0): not green (peras[0]=p); answer has one e -> yellow
    # second e (idx1): peras[1]=e -> green (claims the e)
    # Wait: greens claim first. idx1 guess 'e' vs peras[1]='e' -> GREEN claims e.
    # Then idx0 'e': no e left -> gray.
    assert result[1] == "green"
    assert result[0] == "gray"


def test_duplicate_letter_two_greens():
    # answer "salsa": s,a,l,s,a  (two s, two a)
    result = _tiles("sassy"[:5], "salsa")
    # guess s,a,s,s,y
    # greens: idx0 s==s green; idx1 a==a green; idx2 s vs l no; idx3 s==s green; idx4 y vs a no
    # remaining after greens: salsa counter {s:2,a:2,l:1} minus s(0),a(1),s(3) => {s:0? }
    # s used at 0 and 3 -> two s claimed, a used at 1 -> one a claimed
    # remaining: s:0, a:1, l:1
    # idx2 s: remaining s=0 -> gray; idx4 y -> gray
    assert result == ["green", "green", "gray", "green", "gray"]


def test_emoji_row():
    assert emoji_row([Tile.GREEN, Tile.YELLOW, Tile.GRAY, Tile.GREEN, Tile.GRAY]) == "🟩🟨⬛🟩⬛"


# ── engine flow ─────────────────────────────────────────────────────────────

def test_new_daily_game_is_deterministic():
    eng = WordleEngine()
    a = eng.new_game(mode="daily", user_id="1")
    b = eng.new_game(mode="daily", user_id="2")
    assert a.state["answer"] == b.state["answer"]
    assert a.state["puzzle_no"] == b.state["puzzle_no"]
    # Answer never leaks in client view while playing.
    assert "answer" not in a.client_view


def test_win_flow():
    eng = WordleEngine()
    game = eng.new_game(mode="free", user_id="1")
    answer = game.state["answer"]
    out = eng.submit(state=game.state, guess=answer)
    assert out.state["status"] == "won"
    assert eng.is_over(out.state)
    # Now the client view exposes the result (with answer).
    assert out.client_view["result"]["won"] is True
    assert out.client_view["result"]["answer"] == answer


def test_loss_flow_exhausts_guesses():
    eng = WordleEngine()
    game = eng.new_game(mode="free", user_id="1")
    answer = game.state["answer"]
    # Find a valid wrong guess from the answer list.
    from app.games.wordle.words import ANSWERS
    wrong = next(w for w in ANSWERS if w != answer)
    state = game.state
    for _ in range(6):
        out = eng.submit(state=state, guess=wrong)
        state = out.state
    assert state["status"] == "lost"
    assert out.client_view["result"]["score"] == "X/6"


def test_invalid_guess_rejected():
    eng = WordleEngine()
    game = eng.new_game(mode="free", user_id="1")
    with pytest.raises(GameError):
        eng.submit(state=game.state, guess="zzzzz")  # not in list
    with pytest.raises(GameError):
        eng.submit(state=game.state, guess="abc")  # wrong length


def test_cannot_submit_after_over():
    eng = WordleEngine()
    game = eng.new_game(mode="free", user_id="1")
    answer = game.state["answer"]
    out = eng.submit(state=game.state, guess=answer)
    with pytest.raises(GameError):
        eng.submit(state=out.state, guess=answer)


def test_hostile_state_rejected():
    eng = WordleEngine()
    with pytest.raises(GameError):
        eng.submit(state={"answer": "x", "rows": [], "status": "playing"}, guess="gatos")


def test_malformed_state_shape_rejected():
    # A validly-sealed but wrong-shaped state must 400 cleanly, not KeyError
    # later. Each guard: missing max_guesses, too many rows, bad tile value.
    eng = WordleEngine()
    base = eng.new_game(mode="free", user_id="1").state
    answer = base["answer"]
    guess = next(w for w in ANSWERS if w != answer)

    no_max = {**base, "answer": answer}
    no_max.pop("max_guesses", None)
    with pytest.raises(GameError):
        eng.submit(state=no_max, guess=guess)

    too_many = {**base, "rows": [{"guess": guess, "tiles": ["gray"] * 5}] * 7}
    with pytest.raises(GameError):
        eng.submit(state=too_many, guess=guess)

    bad_tiles = {**base, "rows": [{"guess": guess, "tiles": ["magenta", "x", "y", "z", "w"]}]}
    with pytest.raises(GameError):
        eng.submit(state=bad_tiles, guess=guess)


def test_daily_rejected_after_date_rollover():
    # A daily token saved on an earlier date is no longer playable — closes the
    # "save token, learn answer, finish later, keep streak" gap.
    eng = WordleEngine()
    game = eng.new_game(mode="daily", user_id="1")
    stale = {**game.state, "date": "2020-01-01"}
    with pytest.raises(GameError):
        eng.submit(state=stale, guess=next(w for w in ANSWERS if w != stale["answer"]))
    # Free-play carries no date-gating and is unaffected.
    free = eng.new_game(mode="free", user_id="1")
    free_stale = {**free.state, "date": "2020-01-01"}
    eng.submit(state=free_stale, guess=next(w for w in ANSWERS if w != free_stale["answer"]))


def test_daily_number_and_wrap():
    assert daily_mod.puzzle_number(date(2026, 1, 1)) == 1
    assert daily_mod.puzzle_number(date(2026, 1, 2)) == 2
    # Wrapping: index stays in range.
    from app.games.wordle.words import ANSWERS
    idx = daily_mod.daily_index(date(2030, 1, 1))
    assert 0 <= idx < len(ANSWERS)
