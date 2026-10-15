"""Tests for the Jev experience judge (HTTP mocked; no network)."""
import json

import httpx
import pytest
from app.outpost.rules.model import Params
from app.outpost.sim import experience
from app.outpost.sim.experience import (
    JudgeError,
    experience_metrics,
    judge_run,
)
from app.outpost.sim.runner import RosterEntry, run_round

SMALL = (RosterEntry("builder", 2), RosterEntry("raider", 2))


def _fake_api(seen: list[dict]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        lost = body["state"]["stock_lost_to_raids_in_hours_of_own_production"]
        bad = lost > 0
        return httpx.Response(
            200,
            json={
                "model": "jev-test",
                "answers": {
                    "frustration": {"type": "score", "score": 3.0 if bad else 0.5},
                    "quit_risk": {"type": "noul", "noul": 0.8 if bad else 0.1},
                    "unfair": {"type": "noul", "noul": 0.7 if bad else 0.0},
                    "proud": {"type": "noul", "noul": 0.2 if bad else 0.9},
                },
            },
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_diaries_hide_archetype_and_quitting() -> None:
    result = run_round(Params(), SMALL, seed=3)
    assert set(result.diaries) == {p["player_id"] for p in result.players}
    for diary in result.diaries.values():
        text = json.dumps(diary)
        assert "raider" not in text and "builder" not in text
        assert not any("quit" in k or "stopped" in k for k in diary)


def test_judge_sends_one_request_per_player_and_aggregates() -> None:
    result = run_round(Params(), SMALL, seed=3)
    seen: list[dict] = []
    judge_run(result, client=_fake_api(seen), concurrency=2)
    assert len(seen) == len(result.players)
    assert all(set(b["questions"]) == set(experience.QUESTIONS) for b in seen)
    assert {r["player_id"] for r in result.experience} == set(result.diaries)
    assert 0.5 <= result.metrics["exp_frustration"] <= 3.0
    assert "exp_frustration_raider" in result.metrics


def test_metrics_math() -> None:
    rows = [
        {"archetype": "a", "quit_day": 5, "frustration": 4.0,
         "quit_risk": 0.9, "unfair": 0.8, "proud": 0.1},
        {"archetype": "b", "quit_day": None, "frustration": 0.0,
         "quit_risk": 0.9, "unfair": 0.1, "proud": 0.7},
    ]
    m = experience_metrics(rows)
    assert m["exp_frustration"] == 2.0
    assert m["exp_unfair_share"] == 0.5
    assert m["exp_quit_agreement"] == 0.5  # right about a, wrong about b
    assert m["exp_frustration_a"] == 4.0


def test_api_error_is_reported() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(401, text="no"))
    )
    result = run_round(Params(), SMALL, seed=3)
    with pytest.raises(JudgeError, match="401"):
        judge_run(result, client=client)


def test_missing_key_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(experience.API_KEY_ENV, raising=False)
    result = run_round(Params(), SMALL, seed=3)
    with pytest.raises(JudgeError, match="TYPESAFE_API_KEY"):
        judge_run(result)
