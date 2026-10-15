"""Run one simulated Outpost round with scripted agents.

``run_round`` builds a world, places agents and camps with a seeded RNG,
drives every agent at its check-ins, and returns per-player results, run
metrics, invariant checks, a power/economy series and (optionally) a replay
trace in the dashboard format (local contracts doc).
"""
import math
import random
import statistics
import time
from dataclasses import dataclass, field

from ..engine.core import Engine
from ..engine.state import World
from ..rules.model import (
    BUILD_RES,
    DAY_MS,
    HOUR_MS,
    Params,
    cached,
    value_m,
)
from .agents import ARCHETYPES, Agent, Brain, Controller, Genome

SAMPLE_HOURS = 6
DOMINANCE_BAND = 0.30
FAKE_MAX_VALUE_M = 1_000_000  # parties worth ≤ 1,000 value count as fakes


@dataclass(frozen=True, slots=True)
class RosterEntry:
    """``count`` agents of one archetype; alliance groups of ``group``."""

    archetype: str
    count: int
    join_day: int = 0
    group: int | None = None  # alliance size; None = solo
    genome: Genome | None = None  # overrides the archetype preset


DEFAULT_ROSTER: tuple[RosterEntry, ...] = (
    RosterEntry("builder", 6),
    RosterEntry("raider", 8),
    RosterEntry("turtle", 6),
    RosterEntry("alliance", 8, group=8),
    RosterEntry("alliance", 8, group=4),
    RosterEntry("late", 2, join_day=7),
    RosterEntry("late", 2, join_day=14),
)


@dataclass(slots=True)
class RunResult:
    """Everything a run produces (written to the results DB)."""

    players: list[dict]
    metrics: dict[str, float]
    invariants: list[tuple[str, bool, str]]
    series: list[tuple[int, int, float, float, float, float]]
    trace: dict | None
    wall_s: float
    radius: int
    agents: list[Agent] = field(default_factory=list)
    # player_id -> plain-language facts about that player's round
    diaries: dict[int, dict] = field(default_factory=dict)
    # filled by experience.judge_run when a run is judged
    experience: list[dict] = field(default_factory=list)
    # filled by the CLI from a jev.JevController log
    decisions: list[dict] = field(default_factory=list)


def make_agents(
    roster: tuple[RosterEntry, ...], rng: random.Random
) -> list[Agent]:
    """Expand a roster into agents with ids, timezones and groups."""
    agents: list[Agent] = []
    group_id = 0
    pid = 1
    for entry in roster:
        genome = entry.genome or ARCHETYPES[entry.archetype]
        for i in range(entry.count):
            if entry.group and i % entry.group == 0:
                group_id += 1
            agents.append(
                Agent(
                    player_id=pid,
                    archetype=entry.archetype,
                    genome=genome,
                    tz=rng.randint(-6, 2),
                    join_day=entry.join_day,
                    alliance_group=group_id if entry.group else None,
                )
            )
            pid += 1
    return agents


def _random_tile(
    rng: random.Random,
    engine: Engine,
    min_frac: float,
    max_frac: float,
    spacing: int,
    taken: list[tuple[int, int]],
) -> tuple[int, int]:
    r = engine.w.radius
    for _ in range(5000):
        x, y = rng.randint(-r, r), rng.randint(-r, r)
        d = math.hypot(x, y)
        if not (min_frac * r <= d <= max_frac * r):
            continue
        if not engine._tile_free(x, y):
            continue
        if any(
            (x - a) ** 2 + (y - b) ** 2 < spacing * spacing for a, b in taken
        ):
            continue
        return (x, y)
    raise RuntimeError("map too crowded to place a tile")


def _neighbor(
    engine: Engine, xy: tuple[int, int], taken: list[tuple[int, int]]
) -> tuple[int, int]:
    for dx, dy in ((2, 0), (0, 2), (-2, 0), (0, -2), (2, 2), (-2, -2)):
        cand = (xy[0] + dx, xy[1] + dy)
        if engine._tile_free(*cand) and cand not in taken:
            return cand
    raise RuntimeError("no free tile next to spawn")


def run_round(
    params: Params,
    roster: tuple[RosterEntry, ...] = DEFAULT_ROSTER,
    seed: int = 1,
    *,
    trace: bool = False,
    quit_hours: float = 24.0,
    controllers: dict[str, Controller] | None = None,
) -> RunResult:
    """Simulate one full round and measure it.

    ``controllers`` maps an archetype name to a ``Controller`` that makes
    those agents' key calls (e.g. ``{"jev": JevController(...)}``).
    """
    started = time.perf_counter()
    rng = random.Random(seed)
    agents = make_agents(roster, rng)
    for agent in agents:
        agent.controller = (controllers or {}).get(agent.archetype)
    radius = math.ceil(4 * math.sqrt(len(agents)))
    world = World(
        rules=cached(params),
        radius=radius,
        end_ms=params.round_days * DAY_MS,
        keep_reports=True,
        keep_marches=trace,
    )
    engine = Engine(world)
    engine.start()
    brain = Brain(engine, random.Random(seed * 7919 + 17))

    taken: list[tuple[int, int]] = []
    for agent in agents:
        agent.home_xy = _random_tile(rng, engine, 0.55, 0.95, 3, taken)
        taken.append(agent.home_xy)
    camp_count = math.ceil(len(agents) * params.camps_per_player_x10 / 10)
    for _ in range(camp_count):
        xy = _random_tile(rng, engine, 0.0, 0.95, 2, taken)
        taken.append(xy)
        engine.add_camp(*xy)

    schedule: list[tuple[int, int, Agent | None]] = []
    for agent in agents:
        for t in agent.checkins(params.round_days):
            schedule.append((t, agent.player_id, agent))
    for h in range(0, params.round_days * 24 + 1, SAMPLE_HOURS):
        schedule.append((h * HOUR_MS, -1, None))
    schedule.sort(key=lambda s: (s[0], s[1]))

    series: list[tuple[int, int, float, float, float, float]] = []
    joined: set[int] = set()
    negative_stock = ""
    base_seen: dict[int, list] = {}
    loot_cursor = 0
    recent_loss: dict[int, list[tuple[int, int]]] = {}

    for t, _key, agent in schedule:
        engine.advance(t)
        if world.ended:
            break
        if agent is None:
            negative_stock = negative_stock or _check_stock(world)
            _sample(engine, series, t)
            if trace:
                _track_bases(world, base_seen, t)
            continue
        if agent.player_id not in joined:
            tut = _neighbor(engine, agent.home_xy, taken)
            if engine.join(agent.player_id, agent.home_xy, tut).ok:
                joined.add(agent.player_id)
                _join_group(engine, agents, agent)
            continue
        if agent.quit_day is not None:
            continue
        for entry in world.loot_log[loot_cursor:]:
            recent_loss.setdefault(entry.defender, []).append(
                (entry.t_ms, entry.value_m)
            )
        loot_cursor = len(world.loot_log)
        if _should_quit(engine, agent, recent_loss, quit_hours):
            agent.quit_day = world.now_ms // DAY_MS
            continue
        brain.act(agent)
    engine.advance(world.end_ms)
    _sample(engine, series, world.end_ms)
    negative_stock = negative_stock or _check_stock(world)
    if trace:
        _track_bases(world, base_seen, world.end_ms)

    players = _player_results(engine, agents, series)
    metrics = _metrics(engine, players)
    invariants = _invariants(params, players, negative_stock)
    tr = _trace(engine, agents, base_seen, series, seed) if trace else None
    return RunResult(
        players=players,
        metrics=metrics,
        invariants=invariants,
        series=series,
        trace=tr,
        wall_s=time.perf_counter() - started,
        radius=radius,
        agents=agents,
        diaries=_diaries(engine, agents, series, players),
    )

def _diaries(
    engine: Engine,
    agents: list[Agent],
    series: list[tuple[int, int, float, float, float, float]],
    players: list[dict],
) -> dict[int, dict]:
    """What each player lived through, as facts a reader can judge.

    Deliberately omits archetype and whether the agent quit, so a judge
    reads only the experience (and its quit guess can be checked).
    """
    w = engine.w
    days = w.rules.params.round_days
    weeks = max(1, days // 7)
    by_pid = {p["player_id"]: p for p in players}
    eco: dict[int, list[float]] = {}
    cohort_of = {a.player_id: a.join_day // 7 for a in agents}
    rank_week: dict[int, list[str]] = {}
    cohort_week: dict[int, list[str]] = {}
    for week in range(1, weeks + 1):
        t_h = week * 7 * 24
        snap = sorted(
            ((power, pid) for t, pid, power, *_r in series if t == t_h),
            reverse=True,
        )
        for rank, (_power, pid) in enumerate(snap, 1):
            rank_week.setdefault(pid, []).append(f"{rank} of {len(snap)}")
        cohorts: dict[int, list[int]] = {}
        for _power, pid in snap:
            cohorts.setdefault(cohort_of.get(pid, 0), []).append(pid)
        for members in cohorts.values():
            for rank, pid in enumerate(members, 1):
                cohort_week.setdefault(pid, []).append(
                    f"{rank} of {len(members)}"
                )
    cohort_boards = w.rules.params.cohort_boards > 0
    for _t, pid, _power, e, *_r in series:
        if e > 0:
            eco.setdefault(pid, []).append(e)
    hits: dict[int, list[int]] = {}
    fakes_in: dict[int, int] = {}
    attackers: dict[int, set[int]] = {}
    launched: dict[int, int] = {}
    won: dict[int, int] = {}
    for rep in w.reports:
        if rep["kind"] not in ("raid", "attack"):
            continue
        fake = rep.get("att_value_m", 0) <= FAKE_MAX_VALUE_M
        if not fake:
            launched[rep["attacker"]] = launched.get(rep["attacker"], 0) + 1
            if rep["attacker_won"]:
                won[rep["attacker"]] = won.get(rep["attacker"], 0) + 1
        defender = rep["defender"]
        if not defender or w.bases[rep["base"]].kind != "player":
            continue
        if fake:
            fakes_in[defender] = fakes_in.get(defender, 0) + 1
            continue
        week = min(weeks - 1, int(rep["t_ms"] // (7 * DAY_MS)))
        row = hits.setdefault(defender, [0] * weeks)
        row[week] += 1
        attackers.setdefault(defender, set()).add(rep["attacker"])
    out = {}
    for agent in agents:
        pid = agent.player_id
        p = by_pid.get(pid)
        if p is None:
            continue
        hourly = statistics.median(eco.get(pid, [0.0])) or 1.0
        alliance = w.alliances.get(p["alliance_id"] or 0)
        out[pid] = {
            "round_length_days": days,
            "joined_on_day": agent.join_day + 1,
            "leaderboard_shown_to_you": (
                "players who joined in the same week of the round as you"
                if cohort_boards
                else "every player on the server"
            ),
            "your_rank_on_that_leaderboard_each_week": (
                cohort_week if cohort_boards else rank_week
            ).get(pid, []),
            "server_wide_power_rank_each_week": rank_week.get(pid, []),
            "raided_by_other_players_each_week": hits.get(pid, [0] * weeks),
            "different_players_who_raided_them": len(attackers.get(pid, ())),
            "fake_attacks_received": fakes_in.get(pid, 0),
            "stock_lost_to_raids_in_hours_of_own_production": round(
                p["loot_lost"] / hourly, 1
            ),
            "worst_12h_loss_in_hours_of_own_production": round(
                p["max_12h_loss_hours"], 1
            ),
            "raids_they_launched": launched.get(pid, 0),
            "raids_they_won": won.get(pid, 0),
            "loot_they_gained_in_hours_of_own_production": round(
                p["loot_gained"] / hourly, 1
            ),
            "times_they_evacuated_their_army": p["dodges"],
            "bases_owned": p["bases"],
            "in_an_alliance": alliance is not None,
            "alliance_won_the_round": (
                alliance is not None and w.winner_alliance == alliance.id
            ),
        }
    return out



def _join_group(engine: Engine, agents: list[Agent], agent: Agent) -> None:
    if agent.alliance_group is None:
        return
    mates = [
        a
        for a in agents
        if a.alliance_group == agent.alliance_group
        and a.player_id in engine.w.players
        and a.player_id != agent.player_id
    ]
    leader = next(
        (
            engine.w.players[a.player_id]
            for a in mates
            if engine.w.players[a.player_id].alliance_id is not None
        ),
        None,
    )
    if leader is None:
        engine.create_alliance(
            agent.player_id,
            f"Group {agent.alliance_group}",
            f"G{agent.alliance_group}",
        )
        return
    engine.invite(leader.id, agent.player_id)
    if leader.alliance_id is not None:
        engine.accept_invite(agent.player_id, leader.alliance_id)


def _should_quit(
    engine: Engine,
    agent: Agent,
    recent_loss: dict[int, list[tuple[int, int]]],
    quit_hours: float,
) -> bool:
    now = engine.w.now_ms
    entries = [
        (t, v)
        for t, v in recent_loss.get(agent.player_id, [])
        if now - t <= 72 * HOUR_MS
    ]
    recent_loss[agent.player_id] = entries
    player = engine.w.players[agent.player_id]
    hourly = engine.hourly_value(player)
    return hourly > 0 and sum(v for _t, v in entries) > quit_hours * hourly


def _units_value(engine: Engine, player_id: int) -> int:
    player = engine.w.players[player_id]
    total = 0
    for bid in player.base_ids:
        base = engine.w.bases[bid]
        for stacks in (base.garrison, base.away):
            for unit, n in stacks.items():
                total += engine.r.units[unit].value_m * n
    return total


def _sample(
    engine: Engine,
    series: list[tuple[int, int, float, float, float, float]],
    t: int,
) -> None:
    t_h = t // HOUR_MS
    if series and series[-1][0] == t_h:
        return
    for player in engine.w.players.values():
        stock = 0
        for bid in player.base_ids:
            base = engine.w.bases[bid]
            engine._settle(base)
            stock += value_m({r: base.stock[r] for r in BUILD_RES})
        series.append(
            (
                t_h,
                player.id,
                player.spent_value_m / 1_000_000,
                engine.hourly_value(player) / 1000,
                _units_value(engine, player.id) / 1000,
                stock / 1000,
            )
        )


def _check_stock(world: World) -> str:
    for base in world.bases.values():
        for res, v in base.stock.items():
            if v < 0:
                return f"base {base.id} {res}={v}"
    return ""


def _track_bases(world: World, seen: dict[int, list], t: int) -> None:
    t_h = t / HOUR_MS
    for base in world.bases.values():
        row = seen.get(base.id)
        if row is None:
            seen[base.id] = [base, t_h, None, base.owner, base.kind]
        elif base.removed and row[2] is None:
            row[2] = t_h


def _max_12h_loss_hours(engine: Engine, player_id: int) -> float:
    entries = [e for e in engine.w.loot_log if e.defender == player_id]
    worst = 0.0
    window = 12 * HOUR_MS
    for i, first in enumerate(entries):
        total = 0
        peak = 1
        for e in entries[i:]:
            if e.t_ms - first.t_ms > window:
                break
            total += e.value_m
            peak = max(peak, e.defender_hourly_value_m)
        worst = max(worst, total / peak)
    return worst


def _player_results(
    engine: Engine,
    agents: list[Agent],
    series: list[tuple[int, int, float, float, float, float]],
) -> list[dict]:
    w = engine.w
    gross: dict[int, float] = {}
    for _t, pid, _p, eco, _a, _s in series:
        gross[pid] = gross.get(pid, 0.0) + eco * SAMPLE_HOURS
    gained: dict[int, float] = {}
    gained_players: dict[int, float] = {}
    lost: dict[int, float] = {}
    for rep in w.reports:
        if rep["kind"] not in ("raid", "attack") or not rep["attacker_won"]:
            continue
        v = rep["loot_value_m"] / 1000
        gained[rep["attacker"]] = gained.get(rep["attacker"], 0.0) + v
        if rep["defender"] and w.bases[rep["base"]].kind == "player":
            gained_players[rep["attacker"]] = (
                gained_players.get(rep["attacker"], 0.0) + v
            )
            lost[rep["defender"]] = lost.get(rep["defender"], 0.0) + v
    out = []
    for agent in agents:
        player = w.players.get(agent.player_id)
        if player is None:
            continue
        pid = player.id
        income = gross.get(pid, 0.0) + gained.get(pid, 0.0)
        out.append(
            {
                "player_id": pid,
                "archetype": agent.archetype,
                "tz": agent.tz,
                "joined_day": agent.join_day,
                "final_power": player.spent_value_m / 1_000_000,
                "final_eco": engine.hourly_value(player) / 1000,
                "army_value": _units_value(engine, pid) / 1000,
                "loot_gained": gained.get(pid, 0.0),
                "loot_lost": lost.get(pid, 0.0),
                "raid_income_share": (
                    gained_players.get(pid, 0.0) / income if income else 0.0
                ),
                "max_12h_loss_hours": _max_12h_loss_hours(engine, pid),
                "quit_day": agent.quit_day,
                "alliance_id": player.alliance_id,
                "loot_income_share": (
                    gained.get(pid, 0.0) / income if income else 0.0
                ),
                "bases": len(player.base_ids),
                "fakes_sent": agent.fakes_sent,
                "dodges": agent.dodges,
                "explored": agent.explored,
                "stance": agent.bandit.multiplier,
            }
        )
    return out


def _gini(values: list[float]) -> float:
    vals = sorted(v for v in values if v >= 0)
    n = len(vals)
    if n == 0 or sum(vals) == 0:
        return 0.0
    cum = sum((i + 1) * v for i, v in enumerate(vals))
    return (2 * cum) / (n * sum(vals)) - (n + 1) / n


def archetype_medians(players: list[dict]) -> dict[str, float]:
    """Median final power per archetype."""
    groups: dict[str, list[float]] = {}
    for p in players:
        groups.setdefault(p["archetype"], []).append(p["final_power"])
    return {k: statistics.median(v) for k, v in groups.items()}


def _metrics(engine: Engine, players: list[dict]) -> dict[str, float]:
    w = engine.w
    medians = archetype_medians(players)
    lo = max(1e-9, min(medians.values(), default=1.0))
    hi = max(medians.values(), default=0.0)
    raids_players = sum(
        1
        for r in w.reports
        if r["kind"] in ("raid", "attack")
        and w.bases[r["base"]].kind == "player"
        and r.get("att_value_m", 0) > FAKE_MAX_VALUE_M
    )
    raids_camps = sum(
        1
        for r in w.reports
        if r["kind"] in ("raid", "attack")
        and w.bases[r["base"]].kind in ("camp", "tutorial")
    )
    metrics = {
        "archetype_power_spread": hi / lo,
        "gini_power": _gini([p["final_power"] for p in players]),
        "monument_winner_alliance": float(
            w.winner_alliance if w.winner_alliance is not None else -1
        ),
        "monument_max_level": float(
            max((s.level for s in w.sites.values()), default=0)
        ),
        "quit_rate": (
            sum(1 for p in players if p["quit_day"] is not None)
            / max(1, len(players))
        ),
        "raids_on_players": float(raids_players),
        "raids_on_camps": float(raids_camps),
    }
    for arch, med in medians.items():
        metrics[f"median_power_{arch}"] = med
    stances = [p["stance"] for p in players]
    for mult in sorted(set(stances)):
        share = sum(1 for s in stances if s == mult) / max(1, len(stances))
        metrics[f"final_stance_{mult:g}_share"] = share
    metrics["fakes_sent"] = float(sum(p["fakes_sent"] for p in players))
    metrics["dodges"] = float(sum(p["dodges"] for p in players))
    # Late joiners play the builder preset, so compare like with like.
    founders = [
        p for p in players
        if p["joined_day"] == 0 and p["archetype"] == "builder"
    ]
    late = [p for p in players if p["joined_day"] > 0]
    if founders and late:
        for key, field_name in (("eco", "final_eco"), ("power", "final_power")):
            base = statistics.median(p[field_name] for p in founders)
            mine = statistics.median(p[field_name] for p in late)
            metrics[f"late_{key}_vs_builder"] = mine / base if base else 0.0
    return metrics


def _invariants(
    params: Params, players: list[dict], negative_stock: str
) -> list[tuple[str, bool, str]]:
    cap_hours = 2 * params.bucket_hours + 0.01
    worst = max(players, key=lambda p: p["max_12h_loss_hours"], default=None)
    worst_h = worst["max_12h_loss_hours"] if worst else 0.0
    medians = archetype_medians(players)
    overall = statistics.median([p["final_power"] for p in players] or [0])
    outside = {
        k: round(v / overall, 2) if overall else 0.0
        for k, v in medians.items()
        if overall and abs(v / overall - 1) > DOMINANCE_BAND
    }
    return [
        (
            "p2_loss_cap",
            worst_h <= cap_hours,
            f"worst {worst_h:.2f} h (cap {cap_hours - 0.01:g} h)",
        ),
        ("no_negative_stock", not negative_stock, negative_stock or "ok"),
        (
            "no_archetype_dominates",
            not outside,
            "ok"
            if not outside
            else "outside ±30% of median: "
            + ", ".join(f"{k}={v}" for k, v in sorted(outside.items())),
        ),
    ]


def _trace(
    engine: Engine,
    agents: list[Agent],
    base_seen: dict[int, list],
    series: list[tuple[int, int, float, float, float, float]],
    seed: int,
) -> dict:
    w = engine.w
    marches = list(w.finished_marches) + list(w.marches.values())
    by_player: dict[str, list] = {}
    for t_h, pid, power, eco, army, _stock in series:
        by_player.setdefault(str(pid), []).append([t_h, power, eco, army])
    return {
        "meta": {
            "seed": seed,
            "radius": w.radius,
            "days": w.rules.params.round_days,
            "params": w.rules.params.to_json(),
            "players": [
                {
                    "id": a.player_id,
                    "archetype": a.archetype,
                    "tz": a.tz,
                    "alliance": (
                        w.players[a.player_id].alliance_id
                        if a.player_id in w.players
                        else None
                    ),
                    "color_key": a.player_id,
                }
                for a in agents
            ],
        },
        "bases": [
            {
                "id": base.id,
                "x": base.x,
                "y": base.y,
                "kind": kind,
                "tier": base.tier,
                "owner": owner,
                "from_h": from_h,
                "to_h": to_h,
            }
            for base, from_h, to_h, owner, kind in base_seen.values()
        ],
        "marches": [
            {
                "id": m.id,
                "owner": m.owner,
                "mission": m.mission,
                "from": [w.bases[m.home_base].x, w.bases[m.home_base].y],
                "to": list(m.target_xy),
                "depart_h": m.depart_ms / HOUR_MS,
                "arrive_h": m.arrive_ms / HOUR_MS,
                "return_h": (m.return_ms or m.arrive_ms) / HOUR_MS,
                "outcome": m.outcome or "done",
            }
            for m in marches
        ],
        "battles": [
            {
                "t_h": r["t_ms"] / HOUR_MS,
                "x": r["x"],
                "y": r["y"],
                "attacker": r["attacker"],
                "defender": r["defender"],
                "attacker_won": r["attacker_won"],
                "loot": r.get("loot_value_m", 0) / 1000,
                "kind": r["kind"],
            }
            for r in w.reports
            if r["kind"] in ("raid", "attack")
        ],
        "series": by_player,
    }
