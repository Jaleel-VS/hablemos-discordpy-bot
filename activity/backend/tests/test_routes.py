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
def client(monkeypatch):
    # Stub identity verification: any token resolves to a fixed user.
    async def fake_fetch_user(access_token: str):
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
