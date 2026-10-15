"""Scripted agents for the Outpost simulator.

One parametric policy covers every archetype: an archetype is just a preset
``Genome``, and the searches (``evolve.py``, ``mapelites.py``) mutate the
same fields. Agents act only at their four daily check-ins
(plans/outpost.md §11) and have perfect information about targets, so they
are *stronger* than human players at target selection — exploits they find
are real upper bounds.

Agents also explore and learn within a round (``learning.py``): choices are
sampled with a softmax at temperature ``explore``, raid targets are scored
by experience as well as prediction, and a daily stance bandit tunes army
spending. Beyond raiding, agents can send fakes, focus alliance raids on
one target, and dodge attacks by moving their army out (fleet-saving).
Incoming marches are only "seen" as the target's tower allows (§6.10).

The simulator may use floats and randomness (seeded); the engine never does.
"""
import random
import statistics
from dataclasses import asdict, dataclass, field, fields
from typing import Protocol

from ..engine import combat
from ..engine.core import HOSTILE, Engine
from ..engine.fixed import Q
from ..engine.state import Base, March, Player
from ..rules.model import BUILD_RES, DAY_MS, HOUR_MS, VALUE_PER_UNIT, value_m
from .learning import Bandit, TargetMemory, softmax_pick

OFFENSE = ("lancer", "outrider", "brute")
DEFENSE = ("bulwark", "warden")
COMBAT_UNITS = (*OFFENSE, *DEFENSE)
CHECKIN_HOURS = (7.5, 12.5, 18.0, 22.5)
TARGETS_CONSIDERED = 10
FAKES_PER_CHECKIN = 2
TOWER_SEES_COUNTS = 7


@dataclass(frozen=True, slots=True)
class Genome:
    """Strategy knobs; every field is in [0, 1] except the day fields."""

    army_share: float = 0.1  # share of spare stock spent on units
    defense_ratio: float = 1.0  # share of the army budget on defenders
    raid_players: float = 0.0  # > 0.5 means willing to raid players
    min_return: float = 0.05  # required raid profit / party value
    wall_weight: float = 0.2  # wall target level = 10 × weight
    research_military: float = 0.0  # share of research on arms/armor
    expand_day: float = 10.0  # day to start charter + settlers (> 28: never)
    monument_share: float = 0.0  # share of spare stock sent to the site
    farm_margin: float = 0.2  # food headroom kept above upkeep
    explore: float = 0.1  # softmax temperature / epsilon for choices
    adapt: float = 0.5  # weight of experience vs prediction; 0 = no bandit
    fake_rate: float = 0.0  # chance per check-in to send fakes
    coordinate: float = 0.0  # > 0.5: join the alliance focus target
    dodge: float = 0.0  # > 0.5: evacuate the army from losing fights

    def to_json(self) -> dict[str, float]:
        """Plain dict for storage."""
        return asdict(self)

    @staticmethod
    def bounds() -> dict[str, tuple[float, float]]:
        """Search bounds for each field."""
        b = {f.name: (0.0, 1.0) for f in fields(Genome)}
        b["expand_day"] = (3.0, 30.0)
        return b


ARCHETYPES: dict[str, Genome] = {
    "builder": Genome(),
    "raider": Genome(
        army_share=0.5,
        defense_ratio=0.2,
        raid_players=1.0,
        min_return=0.02,
        wall_weight=0.1,
        research_military=0.6,
        expand_day=40.0,
        fake_rate=0.5,
        coordinate=1.0,
    ),
    "turtle": Genome(
        army_share=0.35,
        defense_ratio=1.0,
        wall_weight=1.0,
        research_military=0.5,
        expand_day=14.0,
        dodge=1.0,
    ),
    "alliance": Genome(
        army_share=0.25,
        defense_ratio=0.5,
        wall_weight=0.4,
        research_military=0.3,
        expand_day=12.0,
        monument_share=0.6,
        coordinate=1.0,
        dodge=1.0,
    ),
    "late": Genome(),
    # Driven by jev.JevController: players and marginal targets are offered
    # (raid_players, min_return) and Jev decides which, if any, to hit.
    "jev": Genome(
        army_share=0.3,
        defense_ratio=0.6,
        raid_players=1.0,
        min_return=0.0,
        wall_weight=0.3,
        research_military=0.4,
        expand_day=40.0,
        explore=0.0,
    ),
}


class Controller(Protocol):
    """Something outside the scripted policy that makes an agent's calls.

    ``decide`` runs at the start of each check-in. It may set
    ``agent.plan`` (``stance``: bandit arm index; ``raid``: {base_id:
    target_id or 0}; ``evacuate``: bool) and returns the genome to use for
    this check-in only.
    """

    def decide(self, brain: "Brain", agent: "Agent", player: Player) -> "Genome":
        """Plan this check-in and return the genome for it."""
        ...


@dataclass(slots=True)
class Agent:
    """A simulated player."""

    player_id: int
    archetype: str
    genome: Genome
    tz: int  # hours from UTC
    join_day: int
    alliance_group: int | None = None
    quit_day: int | None = None
    home_xy: tuple[int, int] = (0, 0)
    bandit: Bandit = field(default_factory=Bandit)
    memory: TargetMemory = field(default_factory=TargetMemory)
    fakes_sent: int = 0
    dodges: int = 0
    explored: int = 0  # choices that weren't the greedy best
    evac: set[int] = field(default_factory=set)  # dodge marches to recall
    # optional outside decision-maker (e.g. jev.JevController)
    controller: "Controller | None" = None
    # this check-in's decisions from the controller (stance/raid/evacuate)
    plan: dict = field(default_factory=dict)

    def next_checkin(self, now_ms: int) -> int:
        """First check-in strictly after ``now_ms``."""
        day = now_ms // DAY_MS - 1
        while True:
            for h in CHECKIN_HOURS:
                t = int((day * 24 + h - self.tz) * HOUR_MS)
                if t > now_ms:
                    return t
            day += 1

    def checkins(self, days: int) -> list[int]:
        """Absolute ms of every check-in from the join day on."""
        out = []
        for day in range(self.join_day, days):
            for h in CHECKIN_HOURS:
                t = int((day * 24 + h - self.tz) * HOUR_MS)
                if day * DAY_MS <= t < days * DAY_MS:
                    out.append(t)
        return sorted(out)


class Brain:
    """Decision logic shared by all agents."""

    def __init__(self, engine: Engine, rng: random.Random | None = None) -> None:
        self.e = engine
        self.w = engine.w
        self.r = engine.r
        self.rng = rng or random.Random(0)
        self.agents: dict[int, Agent] = {}
        self._report_cursor = 0
        self._focus: dict[int, tuple[int, int]] = {}  # alliance -> (day, base)
        self._field_worth: dict[int, float] = {}  # day -> median net worth

    # -------------------------------------------------------------- utils

    def day(self) -> int:
        return self.w.now_ms // DAY_MS

    def _liquid(self, base: Base) -> int:
        return value_m({r: base.stock[r] for r in BUILD_RES})

    def _unit_value(self, units: dict[str, int]) -> int:
        return sum(self.r.units[u].value_m * n for u, n in units.items())

    def net_worth(self, player: Player) -> float:
        """Value spent on buildings/research plus living units (milli)."""
        units = 0
        for bid in player.base_ids:
            base = self.w.bases[bid]
            units += self._unit_value(base.garrison) + self._unit_value(base.away)
        return float(player.spent_value_m + units)

    def _median_worth(self) -> float:
        day = self.day()
        cached = self._field_worth.get(day)
        if cached is None:
            worths = [
                self.net_worth(p)
                for p in self.w.players.values()
                if p.status != "gone"
            ]
            cached = statistics.median(worths) if worths else 1.0
            self._field_worth[day] = cached
        return max(1.0, cached)

    # ------------------------------------------------------------- policy

    def act(self, agent: Agent) -> None:
        """Run one check-in for an agent."""
        player = self.w.players.get(agent.player_id)
        if player is None or player.status == "gone":
            return
        self.agents[agent.player_id] = agent
        self.e.touch(player.id)
        self._learn_from_reports()
        if agent.controller is None:
            self._turn(agent, player)
            return
        saved = agent.genome
        agent.genome = agent.controller.decide(self, agent, player)
        try:
            self._turn(agent, player)
        finally:
            agent.genome = saved
            agent.plan = {}

    def _turn(self, agent: Agent, player: Player) -> None:
        self._update_stance(agent, player)
        for bid in list(player.base_ids):
            base = self.w.bases[bid]
            self._settle_view(base)
            if agent.genome.dodge > 0.5 or "evacuate" in agent.plan:
                self._dodge(agent, player, base)
            self._builds(agent, player, base)
        self._research(agent, player)
        for bid in list(player.base_ids):
            base = self.w.bases[bid]
            self._train(agent, player, base)
            self._raid(agent, player, base)
            if agent.genome.fake_rate > 0:
                self._fakes(agent, player, base)
        self._expand(agent, player)
        if agent.genome.monument_share > 0 and self.day() >= 17:
            self._monument(agent, player)

    # ---------------------------------------------------------- learning

    def _learn_from_reports(self) -> None:
        reports = self.w.reports
        for rep in reports[self._report_cursor :]:
            if rep["kind"] != "raid":
                continue
            agent = self.agents.get(rep["attacker"])
            if agent is None or not rep.get("att_value_m"):
                continue
            profit = rep["loot_value_m"] - rep["att_lost_value_m"]
            agent.memory.record(rep["base"], profit / rep["att_value_m"])
        self._report_cursor = len(reports)

    def _update_stance(self, agent: Agent, player: Player) -> None:
        g = agent.genome
        bandit = agent.bandit
        if agent.plan.get("stance") is not None:
            bandit.current = agent.plan["stance"]
            bandit.days_used[bandit.current] += 1
            return
        if g.adapt <= 0:
            bandit.current = 1  # neutral stance, no learning
            return
        day = self.day()
        if bandit.started_day == day:
            return
        worth = self.net_worth(player)
        field_now = self._median_worth()
        if bandit.started_day >= 0:
            mine = worth / max(1.0, bandit.started_worth)
            others = field_now / max(1.0, bandit.started_field)
            bandit.update(mine / max(1e-9, others))
        bandit.choose(self.rng, g.explore)
        bandit.started_day = day
        bandit.started_worth = worth
        bandit.started_field = field_now

    def _settle_view(self, base: Base) -> None:
        self.e._settle(base)

    # ---------------------------------------------------------- building

    def _builds(self, agent: Agent, player: Player, base: Base) -> None:
        for _ in range(self.e.p.build_slots):
            if len(base.build_queue) >= self.e.p.build_slots:
                return
            choice = self._pick_build(agent, player, base)
            if choice is None or not self.e.build(player.id, base.id, choice).ok:
                return

    def _pick_build(
        self, agent: Agent, player: Player, base: Base
    ) -> str | None:
        e, g = self.e, agent.genome
        lv = {b: e.planned_level(base, b) for b in self.r.buildings}
        hall_cap = self.r.hall_cap(lv["hall"])
        rates = e.rates(base)
        prod_food = rates["food"] + e.upkeep(base)
        wanted: list[str] = []
        if rates["food"] < prod_food * g.farm_margin or rates["food"] <= 0:
            wanted.append("farm")
        day = self.day()
        military = g.army_share >= 0.2 or g.monument_share > 0
        barracks_goal = 1 if day < 1 else (5 if day < 6 else 10)
        if not military:
            barracks_goal = 1 if day >= 2 else 0
        if day + 2 >= g.expand_day:
            barracks_goal = 10  # settlers are tier 3
        if lv["barracks"] < barracks_goal:
            wanted.append("barracks")
        if lv["wall"] < round(10 * g.wall_weight) and lv["barracks"] >= 1:
            wanted.append("wall")
        lab_goal = 3 if day >= 4 else 0
        if g.expand_day < 28:
            lab_goal = max(lab_goal, 3)
        if lv["lab"] < lab_goal and lv["hall"] >= 3:
            wanted.append("lab")
        options: list[tuple[float, str]] = []
        for res in BUILD_RES:
            b = self.r.producer_of[res]
            nxt = lv[b] + 1
            if nxt > self.r.buildings[b].max_level or nxt > hall_cap:
                continue
            gain = (self.r.prod_m[res][nxt] - self.r.prod_m[res][nxt - 1]) * (
                VALUE_PER_UNIT[res]
            )
            options.append(
                (self.r.buildings[b].cost_value_m[nxt] / max(1, gain), b)
            )
        best = min(options) if options else None
        if len(options) > 1 and self.rng.random() < g.explore:
            pick = self.rng.choice(options)
            if pick != best:
                agent.explored += 1
            best = pick
        blocked = best is None or any(
            lv[self.r.producer_of[r]] + 1 > hall_cap for r in BUILD_RES
        )
        if blocked:
            wanted.insert(0, "hall")
        if best is not None:
            wanted.append(best[1])
        wanted.append("hall")
        cap = self.r.cap_m[lv["store"]]
        for wanted_b in wanted:
            b = self._resolve_prereq(base, wanted_b, hall_cap)
            if b is None:
                continue
            nxt = e.planned_level(base, b) + 1
            cost = self.r.buildings[b].cost_m[nxt]
            if any(v > cap * 9 // 10 for v in cost.values()):
                b = "store"
                nxt = e.planned_level(base, b) + 1
                if nxt > self.r.buildings[b].max_level:
                    continue
                cost = self.r.buildings[b].cost_m[nxt]
            if all(base.stock.get(r, 0) >= v for r, v in cost.items()):
                return b
            if wanted_b in ("farm", "hall"):
                return None  # save up for the urgent build
        return None

    def _resolve_prereq(
        self, base: Base, building: str, hall_cap: int
    ) -> str | None:
        """The building itself, or the first unmet requirement under it."""
        e = self.e
        for _ in range(4):
            bdef = self.r.buildings[building]
            nxt = e.planned_level(base, building) + 1
            if nxt > bdef.max_level:
                return None
            if building != "hall" and nxt > hall_cap:
                building = "hall"
                continue
            missing = next(
                (
                    req
                    for req, lvl in bdef.requires.items()
                    if e.planned_level(base, req) < lvl
                ),
                None,
            )
            if missing is None:
                return building
            building = missing
        return None

    def _research(self, agent: Agent, player: Player) -> None:
        if player.research_item is not None:
            return
        g = agent.genome
        order: list[str] = []
        if self.day() >= g.expand_day:
            order.append("charter")
        if g.research_military >= 0.5:
            order += ["arms", "armor", "logistics", "industry"]
        else:
            order += ["industry", "agronomy", "armor", "arms"]
        if self.rng.random() < g.explore:
            self.rng.shuffle(order)
            agent.explored += 1
        for bid in player.base_ids:
            base = self.w.bases[bid]
            if base.buildings.get("lab", 0) == 0:
                continue
            for tech in order:
                if self.e.research(player.id, base.id, tech).ok:
                    return

    # ---------------------------------------------------------- training

    def _train(self, agent: Agent, player: Player, base: Base) -> None:
        g = agent.genome
        if base.buildings.get("barracks", 0) == 0 or base.train_queue:
            return
        share = min(0.95, g.army_share * agent.bandit.multiplier)
        budget = int(self._liquid(base) * share)
        food_room = self.e.rates(base)["food"]
        if food_room <= 0 or budget <= 0:
            return
        plan = [
            (DEFENSE, budget * g.defense_ratio),
            (OFFENSE, budget * (1 - g.defense_ratio)),
        ]
        if g.monument_share > 0 and self.day() >= 15:
            plan.append((("hauler",), budget * 0.2))
        for options, share in plan:
            unit = self._best_unit(base, options)
            if unit is None or share <= 0:
                continue
            udef = self.r.units[unit]
            count = int(share // max(1, udef.value_m))
            count = min(count, food_room // max(1, udef.upkeep_m))
            for r, v in udef.cost_m.items():
                count = min(count, base.stock[r] // v)
            if count > 0 and self.e.train(player.id, base.id, unit, count).ok:
                food_room -= count * udef.upkeep_m

    def _best_unit(self, base: Base, options: tuple[str, ...]) -> str | None:
        level = base.buildings.get("barracks", 0)
        for unit in options:
            tier = self.r.units[unit].tier
            if level >= self.r.barracks_tier_level[tier]:
                return unit
        return None

    # ------------------------------------------------------------ raiding

    def raid_options(
        self, agent: Agent, player: Player, base: Base
    ) -> tuple[dict[str, int], list[tuple[float, Base, tuple[int, float]]]]:
        """The home raid party and every worthwhile target for it."""
        party = {
            u: base.garrison.get(u, 0)
            for u in OFFENSE
            if base.garrison.get(u, 0) > 0
        }
        if not party:
            return party, []
        g = agent.genome
        focus = self._focus_target(agent, player, party)
        options: list[tuple[float, Base, tuple[int, float]]] = []
        for target in self._targets(agent, player, base):
            est = self._estimate(player, party, target)
            if est is None:
                continue
            score = agent.memory.blend(target.id, est[1], g.adapt)
            if score < g.min_return:
                continue
            if focus is not None and target.id == focus:
                score += 0.15  # alliance focus: pile on the same target
            options.append((score, target, est))
        return party, options

    def _raid(self, agent: Agent, player: Player, base: Base) -> None:
        if base.id in agent.plan.get("raid", {}):
            target_id = agent.plan["raid"][base.id]
            party = {
                u: base.garrison.get(u, 0)
                for u in OFFENSE
                if base.garrison.get(u, 0) > 0
            }
            if target_id and party:
                self.e.launch(
                    player.id, base.id, "raid", party, target_base=target_id
                )
            return
        party, options = self.raid_options(agent, player, base)
        if not options:
            return
        g = agent.genome
        scores = [s for s, _t, _e in options]
        i = softmax_pick(scores, 0.3 * g.explore, self.rng)
        if scores[i] < max(scores):
            agent.explored += 1
        self.e.launch(
            player.id, base.id, "raid", party, target_base=options[i][1].id
        )

    def _enemy_bases(self, player: Player) -> list[Base]:
        """Player bases this player may legally attack right now."""
        out = []
        now = self.w.now_ms
        for t in self.w.bases.values():
            if t.removed or t.kind != "player" or t.owner == player.id:
                continue
            owner = self.w.players.get(t.owner or 0)
            if (
                owner is None
                or owner.protection_until > now
                or owner.vacation_state != "none"
                or self.e.affiliated(player.id, owner.id)
            ):
                continue
            out.append(t)
        return out

    def _focus_target(
        self, agent: Agent, player: Player, party: dict[str, int]
    ) -> int | None:
        """Alliance-wide raid target for the day (first member picks)."""
        if agent.genome.coordinate <= 0.5 or player.alliance_id is None:
            return None
        day = self.day()
        current = self._focus.get(player.alliance_id)
        if current is not None and current[0] == day:
            return current[1]
        best: tuple[float, int] | None = None
        for target in self._enemy_bases(player):
            est = self._estimate(player, party, target)
            if est is not None and (best is None or est[1] > best[0]):
                best = (est[1], target.id)
        if best is None:
            return None
        self._focus[player.alliance_id] = (day, best[1])
        return best[1]

    def _targets(
        self, agent: Agent, player: Player, base: Base
    ) -> list[Base]:
        g = agent.genome
        hunts = g.raid_players > 0.5 or (
            g.coordinate > 0.5 and player.alliance_id is not None
        )
        out = []
        for t in self.w.bases.values():
            if t.removed or t.id == base.id:
                continue
            own_tutorial = t.kind == "tutorial" and t.owner == player.id
            enemy = t.kind == "player" and hunts and t.owner != player.id
            if own_tutorial or t.kind == "camp" or enemy:
                out.append(t)
        out.sort(key=lambda t: (t.x - base.x) ** 2 + (t.y - base.y) ** 2)
        near = out[:TARGETS_CONSIDERED]
        focus = self._focus.get(player.alliance_id or 0)
        if focus is not None and focus[0] == self.day():
            extra = self.w.bases.get(focus[1])
            if extra is not None and extra not in near:
                near.append(extra)
        return near

    # --------------------------------------------------- fakes and dodges

    def _fakes(self, agent: Agent, player: Player, base: Base) -> None:
        """Send 1-unit hostile marches to draw out dodging defenders."""
        if self.rng.random() >= agent.genome.fake_rate:
            return
        enemies = self._enemy_bases(player)
        enemies.sort(key=lambda t: (t.x - base.x) ** 2 + (t.y - base.y) ** 2)
        enemies = enemies[:TARGETS_CONSIDERED]
        focus = self._focus.get(player.alliance_id or 0)
        if focus is not None and focus[0] == self.day():
            enemies.sort(key=lambda t: t.id != focus[1])
        for target in enemies[:FAKES_PER_CHECKIN]:
            unit = next(
                (u for u in ("brute", "warden", "outrider") if base.garrison.get(u, 0)),
                None,
            )
            if unit is None:
                return
            res = self.e.launch(
                player.id, base.id, "raid", {unit: 1}, target_base=target.id
            )
            if res.ok:
                agent.fakes_sent += 1

    def _incoming(self, base: Base) -> list[March]:
        return [
            m
            for m in self.w.marches.values()
            if m.status == "outbound"
            and m.target_base == base.id
            and m.mission in HOSTILE
            and m.mission != "scout"
            and m.owner != base.owner
        ]

    def _threatening(self, base: Base, march: March) -> bool:
        """Would this march win? Only knowable with a high tower (§6.10)."""
        if base.buildings.get("tower", 0) < TOWER_SEES_COUNTS:
            return True  # can't see counts: assume the worst
        attacker = self.w.players[march.owner]
        stacks, _loc = self.e._defender_stacks(base)
        if not stacks:
            return False  # nothing to save
        armor = {
            o: self.w.players[o].research.get("armor", 0)
            for o, _u in stacks
            if o in self.w.players
        }
        res = combat.resolve_battle(
            {(attacker.id, u): n for u, n in march.units.items()},
            stacks,
            self.e._stats,
            arms_level=attacker.research.get("arms", 0),
            armor_by_owner=armor,
            wall=base.buildings.get("wall", 0),
            morale_q=Q,
            raid=march.mission == "raid",
        )
        return res.attacker_won

    def threats(self, agent: Agent, base: Base) -> list[March]:
        """Hostile marches landing before the next check-in that look bad."""
        deadline = agent.next_checkin(self.w.now_ms)
        return [
            m
            for m in self._incoming(base)
            if m.arrive_ms <= deadline and self._threatening(base, m)
        ]

    def _dodge(self, agent: Agent, player: Player, base: Base) -> None:
        """Fleet-save: move the army out before a losing fight lands."""
        threats = self.threats(agent, base)
        army = {u: base.garrison.get(u, 0) for u in COMBAT_UNITS}
        army = {u: n for u, n in army.items() if n > 0}
        if not threats:
            self._recall_evacuees(agent, player)
            return
        if not army or not agent.plan.get("evacuate", True):
            return
        land = max(m.arrive_ms for m in threats)
        ally = self._ally_base(player, base)
        if ally is not None:
            res = self.e.launch(
                player.id, base.id, "reinforce", army, target_base=ally.id
            )
        else:
            res = self._fleet_save(agent, player, base, army, land)
        if res is not None and res.ok:
            agent.dodges += 1
            agent.evac.add(res.data["march_id"])

    def _ally_base(self, player: Player, base: Base) -> Base | None:
        if player.alliance_id is None:
            return None
        alliance = self.w.alliances[player.alliance_id]
        options = [
            self.w.bases[bid]
            for pid in sorted(alliance.members)
            if pid != player.id
            for bid in self.w.players[pid].base_ids
        ]
        if not options:
            return None
        return min(
            options, key=lambda t: (t.x - base.x) ** 2 + (t.y - base.y) ** 2
        )

    def _fleet_save(
        self,
        agent: Agent,
        player: Player,
        base: Base,
        army: dict[str, int],
        land: int,
    ):
        """Send the army away from a losing fight; recall it next check-in.

        Best: a camp so far the march is still outbound at the next
        check-in (recalled before any fight). Fallback: a camp the army
        beats that is still far enough to be away when the threat lands.
        """
        now = self.w.now_ms
        safe = max(land, agent.next_checkin(now)) - now
        camps = [
            t
            for t in self.w.bases.values()
            if t.kind == "camp" and not t.removed
        ]
        camps.sort(key=lambda t: (t.x - base.x) ** 2 + (t.y - base.y) ** 2)
        fallback = None
        for camp in camps:
            travel = self.e.travel_ms(player, army, base, (camp.x, camp.y))
            if travel > safe:
                return self.e.launch(
                    player.id, base.id, "raid", army, target_base=camp.id
                )
            if fallback is None and now + 2 * travel > land:
                est = self._estimate(player, army, camp)
                if est is not None and est[1] >= -0.05:
                    fallback = camp
        if fallback is None:
            return None
        return self.e.launch(
            player.id, base.id, "raid", army, target_base=fallback.id
        )

    def _recall_evacuees(self, agent: Agent, player: Player) -> None:
        for march_id in sorted(agent.evac):
            m = self.w.marches.get(march_id)
            if m is not None and m.status in ("outbound", "stationed"):
                self.e.recall(player.id, march_id)
        agent.evac.clear()

    def _estimate(
        self, player: Player, party: dict[str, int], target: Base
    ) -> tuple[int, float] | None:
        e = self.e
        owner = e._owner(target) if target.kind == "player" else None
        if owner is not None and (
            owner.protection_until > self.w.now_ms
            or owner.vacation_state != "none"
            or e.affiliated(player.id, owner.id)
        ):
            return None
        morale = Q
        if owner is not None:
            morale = combat.morale_q(e.military(player), e.military(owner))
        stacks, _loc = e._defender_stacks(target)
        armor = {
            o: self.w.players[o].research.get("armor", 0)
            for o, _u in stacks
            if o in self.w.players
        }
        wall = target.buildings.get("wall", 0) if owner else 0
        res = combat.resolve_battle(
            {(player.id, u): n for u, n in party.items()},
            stacks,
            e._stats,
            arms_level=player.research.get("arms", 0),
            armor_by_owner=armor,
            wall=wall,
            morale_q=morale,
            raid=True,
        )
        lost = sum(
            self.r.units[u].value_m * n for (_o, u), n in res.att_losses.items()
        )
        loot = 0
        if res.attacker_won:
            survivors = {
                u: n - res.att_losses.get((player.id, u), 0)
                for u, n in party.items()
            }
            vault = (
                self.r.vault_m[target.buildings.get("store", 0)] if owner else 0
            )
            exposed = {
                r: max(0, target.stock[r] - vault) * e.p.loot_pct // 100
                for r in BUILD_RES
            }
            bucket = None
            if owner is not None:
                e._settle_bucket(owner)
                bucket = owner.bucket_m
            taken = combat.allocate_loot(
                exposed,
                e._cargo_capacity(player.id, survivors),
                bucket,
                VALUE_PER_UNIT,
            )
            loot = value_m(taken)
        party_value = max(1, self._unit_value(party))
        profit = loot - lost
        return profit, profit / party_value

    # ---------------------------------------------------------- expansion

    def _expand(self, agent: Agent, player: Player) -> None:
        if self.day() < agent.genome.expand_day:
            return
        slots = 1 + player.research.get("charter", 0)
        if len(player.base_ids) + player.reserved_slots >= slots:
            return
        home = self.w.bases[player.base_ids[0]]
        if home.garrison.get("settler", 0) > 0:
            xy = self._free_tile_near(home)
            if xy is not None:
                self.e.launch(
                    player.id, home.id, "settle", {"settler": 1}, target_xy=xy
                )
            return
        if not home.train_queue and home.buildings.get("barracks", 0) >= 10:
            self.e.train(player.id, home.id, "settler", 1)

    def _free_tile_near(self, home: Base) -> tuple[int, int] | None:
        for radius in range(3, 9):
            for dx in range(-radius, radius + 1):
                for dy in (-radius, radius):
                    xy = (home.x + dx, home.y + dy)
                    if self.e._tile_free(*xy) and self.e._spaced(xy):
                        return xy
        return None

    # ----------------------------------------------------------- monument

    def _monument(self, agent: Agent, player: Player) -> None:
        if player.alliance_id is None:
            return
        own = next(
            (
                s
                for s in self.w.sites.values()
                if s.alliance_id == player.alliance_id
            ),
            None,
        )
        home = self.w.bases[player.base_ids[0]]
        if own is None:
            self._attack_site(player, home)
            return
        site_base = self.w.bases[own.base_id]
        need = self.r.monument_recipe_m[min(own.level + 1, len(self.r.monument_recipe_m) - 1)]
        missing = {
            r: max(0, need[r] - own.contributed[r]) for r in BUILD_RES
        }
        haulers = home.garrison.get("hauler", 0)
        if own.state != "building" and haulers and any(missing.values()):
            budget = int(self._liquid(home) * agent.genome.monument_share)
            cap_m = self.e._cargo_capacity(player.id, {"hauler": haulers}) * 1000
            cargo = {}
            room = cap_m
            for r in BUILD_RES:
                give = min(
                    missing[r],
                    home.stock[r] * agent.genome.monument_share,
                    room,
                    budget * 1000 // VALUE_PER_UNIT[r],
                )
                give = int(give)
                if give > 0:
                    cargo[r] = give
                    room -= give
            if cargo:
                need_units = -(-sum(cargo.values()) // (self.r.units["hauler"].cargo * 1000))
                self.e.launch(
                    player.id,
                    home.id,
                    "contribute",
                    {"hauler": min(haulers, max(1, need_units))},
                    target_base=site_base.id,
                    cargo=cargo,
                )
        defenders = {u: home.garrison.get(u, 0) // 2 for u in DEFENSE}
        if any(defenders.values()) and self.day() >= 18:
            self.e.launch(
                player.id,
                home.id,
                "reinforce",
                defenders,
                target_base=site_base.id,
            )

    def _attack_site(self, player: Player, home: Base) -> None:
        party = {
            u: home.garrison.get(u, 0)
            for u in (*OFFENSE, "ram")
            if home.garrison.get(u, 0) > 0
        }
        if not party:
            return
        for site in sorted(self.w.sites.values(), key=lambda s: s.base_id):
            target = self.w.bases[site.base_id]
            stacks, _l = self.e._defender_stacks(target)
            if not stacks:
                stacks = {}
            armor = {
                o: self.w.players[o].research.get("armor", 0)
                for o, _u in stacks
                if o in self.w.players
            }
            atk = sum(self.r.units[u].atk * n for u, n in party.items())
            if atk <= 0:
                return
            res = combat.resolve_battle(
                {(player.id, u): n for u, n in party.items()},
                stacks,
                self.e._stats,
                arms_level=player.research.get("arms", 0),
                armor_by_owner=armor,
                wall=0,
                morale_q=Q,
                raid=False,
            )
            if res.attacker_won:
                self.e.launch(
                    player.id, home.id, "attack", party, target_base=target.id
                )
                return
