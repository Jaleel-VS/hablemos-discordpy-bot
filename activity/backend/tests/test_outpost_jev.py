"""Tests for Jev-controlled players (HTTP mocked; no network)."""
import json
from pathlib import Path

import httpx
from app.outpost.rules.model import Params
from app.outpost.sim.jev import JevCache, JevController, decision_metrics
from app.outpost.sim.runner import RosterEntry, run_round

ROSTER = (
    RosterEntry("builder", 3),
    RosterEntry("raider", 3),
    RosterEntry("jev", 2),
)


def _fake_jev(seen: list[dict], *, raid: str = "t1") -> httpx.Client:
    """Always: military stance, expand, raid ``raid``, evacuate."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        answers = {}
        for qid, q in body["questions"].items():
            options = list(q["criteria"])
            want = {
                "stance": "military",
                "priority": "expand",
                "raid": raid if raid in options else "none",
                "response": "evacuate",
            }[qid]
            answers[qid] = {
                "type": "choice",
                "choice": want,
                "probabilities": {o: float(o == want) for o in options},
                "confidence": 1.0,
            }
        return httpx.Response(200, json={"model": "jev-test", "answers": answers})

    return httpx.Client(transport=httpx.MockTransport(handler))


def _run(controller: JevController, seed: int = 4):
    return run_round(
        Params(), ROSTER, seed=seed, controllers={"jev": controller}
    )


def test_jev_decisions_drive_the_player() -> None:
    seen: list[dict] = []
    jev = JevController(client=_fake_jev(seen))
    result = _run(jev)
    jev_players = [p for p in result.players if p["archetype"] == "jev"]
    assert jev_players and seen
    # stance/priority asked once per in-game day per Jev player, not more
    daily = [b for b in seen if "stance" in b["questions"]]
    assert len(daily) <= 2 * Params().round_days
    # military stance every day → the final stance is the high arm
    assert all(p["stance"] == 1.6 for p in jev_players)
    # "expand" daily → Jev players found extra bases
    assert max(p["bases"] for p in jev_players) > 1
    metrics = decision_metrics(jev.log)
    assert metrics["jev_stance_military_share"] == 1.0


def test_choosing_none_means_no_raids() -> None:
    jev = JevController(client=_fake_jev([], raid="none"))
    result = _run(jev)
    jev_ids = {p["player_id"] for p in result.players if p["archetype"] == "jev"}
    assert not any(
        d["question"] == "raid" and d["choice"] != "none" for d in jev.log
    )
    assert all(
        p["loot_gained"] == 0 for p in result.players
        if p["player_id"] in jev_ids
    )


def test_cache_replays_without_the_api(tmp_path: Path) -> None:
    cache = tmp_path / "jev.sqlite"
    seen: list[dict] = []
    first = _run(JevController(client=_fake_jev(seen), cache=JevCache(cache)))

    def offline(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("cache miss hit the network")

    replay_ctl = JevController(
        client=httpx.Client(transport=httpx.MockTransport(offline)),
        cache=JevCache(cache),
    )
    replay = _run(replay_ctl)
    assert replay_ctl.calls == 0 and replay_ctl.cache_hits == len(seen)
    assert replay.players == first.players
