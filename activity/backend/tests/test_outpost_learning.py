"""Tests for in-round learning, dodging and the MAP-Elites archive."""
import random

from app.outpost.engine.core import Engine
from app.outpost.engine.state import World
from app.outpost.rules.model import DAY_MS, Params, cached
from app.outpost.sim.agents import Agent, Brain, Genome
from app.outpost.sim.learning import Bandit, TargetMemory, softmax_pick
from app.outpost.sim.mapelites import Archive, Elite

# ── learners ───────────────────────────────────────────────────────────────


def test_bandit_tries_every_arm_then_exploits_best() -> None:
    bandit = Bandit()
    rng = random.Random(1)
    tried = []
    for reward in (0.9, 1.4, 1.0):
        tried.append(bandit.choose(rng, epsilon=0.0))
        bandit.update(reward)
    assert sorted(tried) == [0, 1, 2]
    assert all(bandit.choose(rng, epsilon=0.0) == 1 for _ in range(5))


def test_bandit_explores_with_epsilon() -> None:
    bandit = Bandit(counts=[5, 5, 5], means=[0.0, 2.0, 0.0])
    rng = random.Random(3)
    picks = {bandit.choose(rng, epsilon=1.0) for _ in range(50)}
    assert picks == {0, 1, 2}


def test_target_memory_moves_toward_experience() -> None:
    mem = TargetMemory()
    assert mem.blend(7, 0.5, adapt=0.5) == 0.5  # no experience: prediction
    mem.record(7, -1.0)
    assert mem.blend(7, 0.5, adapt=0.5) == -0.25
    mem.record(7, 1.0)
    assert -1.0 < mem.ema[7] < 1.0


def test_softmax_is_greedy_at_zero_temperature() -> None:
    rng = random.Random(0)
    assert all(softmax_pick([0.1, 0.9, 0.5], 0.0, rng) == 1 for _ in range(20))
    hot = {softmax_pick([0.1, 0.9, 0.5], 5.0, rng) for _ in range(200)}
    assert hot == {0, 1, 2}


# ── archive ────────────────────────────────────────────────────────────────


def test_archive_keeps_fittest_per_cell_and_clamps() -> None:
    arc = Archive(4, 4, 1.0, 1.0)
    g = Genome()
    assert arc.insert(Elite(g, 1.0, (0.1, 0.1), 0))
    assert not arc.insert(Elite(g, 0.8, (0.2, 0.2), 1))  # same cell, worse
    assert arc.insert(Elite(g, 1.2, (0.2, 0.2), 2))
    assert arc.insert(Elite(g, 0.5, (9.0, -3.0), 3))  # clamps to (3, 0)
    assert set(arc.cells) == {(0, 0), (3, 0)}
    assert arc.cells[(0, 0)].fitness == 1.2
    assert arc.coverage == 2 / 16
    assert arc.qd_score == 1.7


# ── dodging (fleet-save) ───────────────────────────────────────────────────


def _duel(tower: int, attackers: int) -> tuple[Engine, Brain, Agent]:
    world = World(rules=cached(Params()), radius=26, end_ms=28 * DAY_MS)
    e = Engine(world)
    e.start()
    assert e.join(1, (0, 0), (2, 0)).ok
    assert e.join(2, (5, 0), (5, 2)).ok
    e.add_camp(-12, 0)
    assert e.join(3, (-6, 0), (-6, 2)).ok
    aid = e.create_alliance(1, "Home", "HM").data["alliance_id"]
    e.invite(1, 3)
    assert e.accept_invite(3, aid).ok
    for p in world.players.values():
        p.protection_until = 0
    home = world.bases[world.players[1].base_ids[0]]
    home.garrison = {"warden": 20}
    home.buildings["tower"] = tower
    raider = world.bases[world.players[2].base_ids[0]]
    raider.garrison = {"brute": attackers}
    assert e.launch(2, raider.id, "raid", {"brute": attackers},
                    target_base=home.id).ok
    agent = Agent(1, "turtle", Genome(dodge=1.0, explore=0.0, adapt=0.0),
                  tz=0, join_day=0)
    return e, Brain(e, random.Random(0)), agent


def test_dodger_evacuates_from_a_losing_fight() -> None:
    e, brain, agent = _duel(tower=0, attackers=500)
    brain.act(agent)
    home = e.w.bases[e.w.players[1].base_ids[0]]
    assert home.garrison.get("warden", 0) == 0
    assert agent.dodges == 1
    e.advance(2 * 3_600_000)
    stationed = [m for m in e.w.marches.values()
                 if m.owner == 1 and m.status == "stationed"]
    assert stationed and stationed[0].units["warden"] == 20  # safe at the ally


def test_without_tower_a_fake_still_triggers_a_dodge() -> None:
    _e, brain, agent = _duel(tower=0, attackers=1)
    brain.act(agent)
    assert agent.dodges == 1


def test_high_tower_sees_through_fakes() -> None:
    e, brain, agent = _duel(tower=7, attackers=1)
    brain.act(agent)
    home = e.w.bases[e.w.players[1].base_ids[0]]
    assert agent.dodges == 0
    assert home.garrison.get("warden", 0) == 20
