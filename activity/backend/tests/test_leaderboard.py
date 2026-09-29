"""Per-server daily leaderboard: ranking order and guild/name attribution.

Ranking is a pure function, tested with hand-worked rows. Attribution is tested
through the real routes with a fake DB that captures what would be persisted.
"""
from datetime import datetime, timedelta

import app.games.routes as routes_mod
import pytest
from app.db import rank_daily
from fastapi import FastAPI
from fastapi.testclient import TestClient

T0 = datetime(2026, 1, 1, 12, 0, 0)


def _row(user_id, name, *, won=True, at=0, **payload):
    return {
        "user_id": user_id, "user_name": name, "won": won,
        "created_at": T0 + timedelta(minutes=at), "payload": payload,
    }


def _order(rows):
    return [e["name"] for e in rank_daily(rows)]


def test_wordle_fewer_guesses_first_then_earlier_finisher():
    rows = [
        _row(1, "slow4", guesses_used=4, at=0),
        _row(2, "quick2", guesses_used=2, at=5),
        _row(3, "also4_later", guesses_used=4, at=9),
    ]
    assert _order(rows) == ["quick2", "slow4", "also4_later"]


def test_wordle_loss_ranks_below_any_win():
    rows = [
        _row(1, "lost", won=False, guesses_used=6, at=0),
        _row(2, "won_late", guesses_used=6, at=9),
    ]
    assert _order(rows) == ["won_late", "lost"]


def test_sprint_games_rank_more_correct_first():
    # guesses_used equals correct for these games, so ranking by fewest
    # guesses would put the worst player first — this pins the right direction.
    rows = [
        _row(1, "low", correct=3, guesses_used=3, at=0),
        _row(2, "high", correct=9, guesses_used=9, at=5),
    ]
    assert _order(rows) == ["high", "low"]


def test_entries_carry_rank_string_id_and_score():
    big_id = 1234567890123456789  # beyond JS Number.MAX_SAFE_INTEGER
    [entry] = rank_daily([_row(big_id, "ana", guesses_used=3, score="3/6")])
    assert entry == {"rank": 1, "user_id": str(big_id), "name": "ana", "score": "3/6"}


# ── attribution + endpoint, through the real router ────────────────────────


class FakeDB:
    def __init__(self):
        self.recorded: list[dict] = []
        self.board_calls: list[dict] = []

    async def has_daily_result(self, **_):
        return False

    async def start_session(self, **_):
        pass

    async def end_session(self, **_):
        pass

    async def record_result(self, **kwargs):
        self.recorded.append(kwargs)
        return True

    async def daily_leaderboard(self, *, game_key, guild_id, limit=10):
        self.board_calls.append({"game_key": game_key, "guild_id": guild_id})
        return {"puzzle_no": 7, "entries": [{"rank": 1, "user_id": "42",
                                              "name": "tester", "score": "9/10"}]}


@pytest.fixture
def db():
    return FakeDB()


@pytest.fixture
def client(monkeypatch, db):
    async def fake_fetch_user(access_token: str):
        return {"id": "42", "username": "tester", "global_name": "", "avatar": ""}

    monkeypatch.setattr(routes_mod, "fetch_user", fake_fetch_user)
    app = FastAPI()
    app.include_router(routes_mod.build_router(
        get_db=lambda: db,
        get_secret=lambda: "test-secret-for-sealing",
        discord_context={"channel_id": None, "guild_id": None},
    ))
    with TestClient(app) as c:
        yield c


def _play_conjugation_to_the_end(client, **start_extra):
    start = client.post(
        "/api/games/conjugation/start",
        json={"access_token": "t", "mode": "free", "options": {"timed": False},
              **start_extra},
    ).json()
    return client.post(
        "/api/games/conjugation/guess",
        json={"access_token": "t", "sealed_state": start["sealed_state"],
              "guess": "", "finish": True},
    )


def test_finished_game_persists_guild_and_display_name(client, db):
    # Discord sends snowflakes as strings; they must coerce to int for BIGINT.
    r = _play_conjugation_to_the_end(client, guild_id="987654321098765432")
    assert r.status_code == 200
    [saved] = db.recorded
    assert saved["guild_id"] == 987654321098765432
    assert saved["user_name"] == "tester"


def test_dm_launch_persists_no_guild(client, db):
    _play_conjugation_to_the_end(client)
    assert db.recorded[0]["guild_id"] is None


def test_attribution_never_reaches_the_client_view(client):
    r = _play_conjugation_to_the_end(client, guild_id="123")
    dumped = str(r.json()["view"])
    assert "_gid" not in dumped and "_uname" not in dumped


@pytest.mark.parametrize("bad", [0, -5, 2**63])
def test_out_of_range_guild_id_rejected(client, bad):
    r = client.post(
        "/api/games/conjugation/start",
        json={"access_token": "t", "mode": "free", "guild_id": bad},
    )
    assert r.status_code == 422


def test_leaderboard_queries_the_requested_guild_and_game(client, db):
    r = client.post(
        "/api/games/cloze/leaderboard",
        json={"access_token": "t", "guild_id": "555"},
    )
    assert r.status_code == 200
    assert r.json()["puzzle_no"] == 7
    assert db.board_calls == [{"game_key": "cloze", "guild_id": 555}]


def test_leaderboard_without_guild_is_empty_and_skips_the_db(client, db):
    r = client.post("/api/games/cloze/leaderboard", json={"access_token": "t"})
    assert r.json() == {"puzzle_no": None, "entries": []}
    assert db.board_calls == []


def test_leaderboard_unknown_game_404(client):
    r = client.post("/api/games/nope/leaderboard", json={"access_token": "t", "guild_id": "1"})
    assert r.status_code == 404
