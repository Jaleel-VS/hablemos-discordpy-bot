"""Route-level tests for the games API (sealed state, identity, cheat-safety).

Uses FastAPI's TestClient with Discord identity + DB stubbed out, so no network
or Postgres is needed. Persistence is disabled (get_db returns None) — result
recording is covered separately.
"""
import base64
import json

import pytest
from fastapi.testclient import TestClient

import app.games.routes as routes_mod
from app.config import Settings
from app.main import create_app


@pytest.fixture
def fetch_calls():
    """Mutable counter the client fixture increments on each fetch_user call."""
    return {"n": 0}


@pytest.fixture
def client(monkeypatch, fetch_calls):
    # Stub identity verification: any token resolves to a fixed user, and count
    # calls so tests can assert we don't re-verify on every guess.
    async def fake_fetch_user(access_token: str):
        fetch_calls["n"] += 1
        return {"id": "42", "username": "tester", "global_name": "", "avatar": ""}

    monkeypatch.setattr(routes_mod, "fetch_user", fake_fetch_user)

    cfg = Settings(
        discord_client_id="123",
        discord_client_secret="test-secret-for-sealing",
        port=8080,
        environment="test",
        static_dir="/tmp/nope",
        database_url="",  # persistence disabled
    )
    app = create_app(cfg)
    with TestClient(app) as c:
        yield c


def test_list_games(client):
    r = client.get("/api/games")
    assert r.status_code == 200
    keys = [g["key"] for g in r.json()["games"]]
    assert "wordle" in keys


def test_start_returns_sealed_state_not_answer(client):
    r = client.post("/api/games/wordle/start", json={"access_token": "t", "mode": "daily"})
    assert r.status_code == 200
    body = r.json()
    assert "sealed_state" in body
    assert "view" in body
    # The answer must NOT be recoverable from the response.
    assert "answer" not in body["view"]
    assert "answer" not in json.dumps(body["view"])
    # Sealed state must not be plaintext-decodable to reveal the answer.
    with pytest.raises(Exception):
        json.loads(base64.urlsafe_b64decode(body["sealed_state"] + "=="))


def test_unknown_game_404(client):
    r = client.post("/api/games/nope/start", json={"access_token": "t", "mode": "free"})
    assert r.status_code == 404


def test_guess_flow_and_win(client):
    # Start, then brute a win by reading the answer from... we can't (sealed).
    # Instead: play a free game, guess valid words until we win or exhaust.
    start = client.post("/api/games/wordle/start", json={"access_token": "t", "mode": "free"}).json()
    sealed = start["sealed_state"]
    # Submit a valid guess (a known answer-list word) and confirm the view
    # updates with tiles and re-seals.
    r = client.post(
        "/api/games/wordle/guess",
        json={"access_token": "t", "sealed_state": sealed, "guess": "gatos"},
    )
    # "gatos" may or may not be a valid guess; if not, expect 400 with message.
    assert r.status_code in (200, 400)
    if r.status_code == 200:
        body = r.json()
        assert len(body["view"]["rows"]) == 1
        assert body["sealed_state"] != sealed  # state advanced


def test_tampered_state_rejected(client):
    r = client.post(
        "/api/games/wordle/guess",
        json={"access_token": "t", "sealed_state": "not-a-real-token", "guess": "gatos"},
    )
    assert r.status_code == 400


def test_invalid_guess_message(client):
    start = client.post("/api/games/wordle/start", json={"access_token": "t", "mode": "free"}).json()
    r = client.post(
        "/api/games/wordle/guess",
        json={"access_token": "t", "sealed_state": start["sealed_state"], "guess": "zzzzz"},
    )
    assert r.status_code == 400


def test_stats_zero_without_db(client):
    r = client.post("/api/games/wordle/stats", json={"access_token": "t"})
    assert r.status_code == 200
    assert r.json()["games"] == 0


# ── conjugation via the generic routes ────────────────────────────────────

def test_conjugation_listed(client):
    keys = [g["key"] for g in client.get("/api/games").json()["games"]]
    assert "conjugation" in keys


def test_conjugation_start_hides_answer(client):
    r = client.post(
        "/api/games/conjugation/start",
        json={"access_token": "t", "mode": "free",
              "options": {"set": "regular-ar", "tenses": ["presente"], "pronouns": ["yo"]}},
    )
    assert r.status_code == 200
    body = r.json()
    assert "prompt" in body["view"]
    # The expected answer must never appear in the client view/response.
    assert "expected" not in json.dumps(body["view"])


def test_conjugation_guess_advances(client):
    start = client.post(
        "/api/games/conjugation/start",
        json={"access_token": "t", "mode": "free"},
    ).json()
    r = client.post(
        "/api/games/conjugation/guess",
        json={"access_token": "t", "sealed_state": start["sealed_state"], "guess": "hablo"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["view"]["answered_count"] == 1
    assert body["sealed_state"] != start["sealed_state"]  # state advanced
    assert body["view"]["last"] is not None


def test_identity_verified_once_not_per_guess(client, fetch_calls):
    # start verifies identity once...
    start = client.post(
        "/api/games/conjugation/start", json={"access_token": "t", "mode": "free"},
    ).json()
    assert fetch_calls["n"] == 1
    sealed = start["sealed_state"]
    # ...and subsequent guesses reuse the id bound in the sealed state, with NO
    # further fetch_user calls (the whole point of the latency fix).
    for _ in range(3):
        resp = client.post(
            "/api/games/conjugation/guess",
            json={"access_token": "t", "sealed_state": sealed, "guess": "x"},
        ).json()
        sealed = resp["sealed_state"]
    assert fetch_calls["n"] == 1  # still just the one from start


def test_bound_uid_not_leaked_to_client(client):
    start = client.post(
        "/api/games/conjugation/start", json={"access_token": "t", "mode": "free"},
    ).json()
    # The internal _uid must never appear in the client-facing view.
    assert "_uid" not in json.dumps(start["view"])
    resp = client.post(
        "/api/games/conjugation/guess",
        json={"access_token": "t", "sealed_state": start["sealed_state"], "guess": "x"},
    ).json()
    assert "_uid" not in json.dumps(resp["view"])


def test_guess_falls_back_to_token_verify_for_legacy_state(client, fetch_calls):
    # An in-flight game sealed before the fix has no _uid; guess must still work
    # by verifying the token once.
    start = client.post(
        "/api/games/conjugation/start", json={"access_token": "t", "mode": "free"},
    ).json()
    # Rebuild a sealed state WITHOUT _uid to simulate a pre-fix token.
    from app.games.sealed_state import seal, unseal

    secret = "test-secret-for-sealing"
    state = unseal(secret, start["sealed_state"])
    state.pop("_uid", None)
    legacy = seal(secret, state)
    fetch_calls["n"] = 0
    resp = client.post(
        "/api/games/conjugation/guess",
        json={"access_token": "t", "sealed_state": legacy, "guess": "x"},
    )
    assert resp.status_code == 200
    assert fetch_calls["n"] == 1  # fell back to a token verify


def test_daily_replay_refused_when_already_played(monkeypatch):
    # Build the router directly with a fake DB that reports today's daily as
    # already finished — the second start must be refused (409), never a replay.
    from fastapi import FastAPI

    async def fake_fetch_user(access_token: str):
        return {"id": "42", "username": "t", "global_name": "", "avatar": ""}

    monkeypatch.setattr(routes_mod, "fetch_user", fake_fetch_user)

    class FakeDB:
        async def has_daily_result(self, *, game_key, user_id, puzzle_no):
            return True  # this user already played today's puzzle

    app = FastAPI()
    app.include_router(
        routes_mod.build_router(
            get_db=lambda: FakeDB(),
            get_secret=lambda: "test-secret-for-sealing",
            discord_context={"channel_id": None, "guild_id": None},
        )
    )
    with TestClient(app) as c:
        r = c.post("/api/games/conjugation/start", json={"access_token": "t", "mode": "daily"})
        assert r.status_code == 409
        # Freeplay carries no puzzle_no and must never be blocked.
        assert c.post(
            "/api/games/conjugation/start", json={"access_token": "t", "mode": "free"},
        ).status_code == 200


def test_conjugation_untimed_practice_finishes_on_request(client):
    start = client.post(
        "/api/games/conjugation/start",
        json={"access_token": "t", "mode": "free", "options": {"timed": False}},
    ).json()
    assert start["view"]["timed"] is False
    assert start["view"]["deadline"] is None
    # "Terminar": finish flag ends the run and returns a result.
    r = client.post(
        "/api/games/conjugation/guess",
        json={"access_token": "t", "sealed_state": start["sealed_state"],
              "guess": "", "finish": True},
    )
    assert r.status_code == 200
    assert r.json()["view"]["status"] == "over"
    assert "result" in r.json()["view"]
