"""Outpost engine: time advance, settlement, events and player actions.

Implements plans/outpost.md §6–7 over the mutable ``World``. The engine is
deterministic: no wall clock, no randomness, integer math only. Callers
(the sim today, the Activity round transaction later) call ``advance`` to
drain due events and then one action method.

Invariant: anything that changes a base's production or upkeep rates first
settles that base (and its owner's loot bucket) to ``world.now_ms``, so the
interval since ``settled_ms`` is always linear.
"""
import heapq
from dataclasses import dataclass, field
from math import isqrt

from ..rules.model import (
    BUILD_RES,
    DAY_MS,
    HOUR_MS,
    MILLI,
    RESOURCES,
    VALUE_PER_UNIT,
    value_m,
)
from . import combat
from .fixed import Q
from .state import (
    Alliance,
    Base,
    LaneItem,
    LootEntry,
    March,
    Membership,
    Player,
    Site,
    World,
)

HOSTILE = frozenset({"raid", "attack", "scout"})
MISSIONS = frozenset(
    {
        "raid",
        "attack",
        "scout",
        "reinforce",
        "transport",
        "settle",
        "contribute",
    }
)
MIN_TRAVEL_MS = 5 * 60 * 1000
MAX_TRAIN_BATCHES = 5
START_STOCK = {"ore": 600, "wood": 600, "gem": 100, "food": 300}
NEW_BASE_STOCK = 500
TUTORIAL_STOCK = {"ore": 500, "wood": 500, "gem": 200}
SITE_GARRISON = {"warden": 256, "bulwark": 32}


@dataclass(frozen=True, slots=True)
class Result:
    """Outcome of an action: accepted, or rejected with a reason code."""

    ok: bool
    code: str = "ok"
    data: dict = field(default_factory=dict)


def _reject(code: str) -> Result:
    return Result(False, code)


def _accept(**data: object) -> Result:
    return Result(True, "ok", dict(data))


class Engine:
    """All rules that mutate a ``World``."""

    def __init__(self, world: World) -> None:
        self.w = world
        self.r = world.rules
        self.p = world.rules.params
        self._stats = {
            u.id: combat.UnitStats(
                atk=u.atk,
                cls=u.cls,
                def_foot=u.def_foot,
                def_swift=u.def_swift,
                cargo=u.cargo,
                value_m=u.value_m,
            )
            for u in self.r.units.values()
        }

    # ------------------------------------------------------------------
    # scheduling
    # ------------------------------------------------------------------

    def _schedule(self, due_ms: int, kind: str, *ref: int) -> None:
        w = self.w
        w.seq += 1
        heapq.heappush(w.events, (max(due_ms, w.now_ms), w.seq, kind, ref))

    def _dur(self, ms: int) -> int:
        """Scale a speed-1.0 duration by round speed (ceil)."""
        return max(1, -(-ms * 100 // self.p.speed_pct))

    def advance(self, until_ms: int) -> None:
        """Process every event with ``due_ms <= until_ms`` in order.

        Clamped to the round end; at the end the barrier runs (§6.18).
        """
        w = self.w
        if w.ended:
            return
        limit = min(until_ms, w.end_ms)
        while w.events and w.events[0][0] <= limit and not w.ended:
            due, _seq, kind, ref = heapq.heappop(w.events)
            w.now_ms = max(w.now_ms, due)
            getattr(self, "_ev_" + kind)(*ref)
        if not w.ended:
            w.now_ms = max(w.now_ms, limit)
            if limit >= w.end_ms:
                self._end_round()

    def start(self) -> None:
        """Schedule round-level phase events (call once after setup)."""
        p = self.p
        self._schedule((p.site_day - 1) * DAY_MS - DAY_MS, "qualify")
        self._schedule((p.site_day - 1) * DAY_MS, "spawn_sites")
        for day in range(1, p.round_days):
            self._schedule(day * DAY_MS, "daily")

    # ------------------------------------------------------------------
    # rates and settlement
    # ------------------------------------------------------------------

    def _owner(self, base: Base) -> Player | None:
        return self.w.players.get(base.owner) if base.owner else None

    def _producing(self, base: Base) -> bool:
        owner = self._owner(base)
        return (
            base.kind == "player"
            and owner is not None
            and owner.status != "gone"
            and owner.vacation_state != "active"
        )

    def rates(self, base: Base) -> dict[str, int]:
        """Current per-hour rates in milli-units (food is net of upkeep)."""
        rates = dict.fromkeys(RESOURCES, 0)
        if not self._producing(base):
            return rates
        owner = self._owner(base)
        if owner is None:
            return rates
        industry = owner.research.get("industry", 0)
        agronomy = owner.research.get("agronomy", 0)
        boost = 100 + (
            owner.catchup_pct if self.w.now_ms < owner.catchup_until else 0
        )
        for res in RESOURCES:
            level = base.buildings.get(self.r.producer_of[res], 0)
            base_rate = self.r.prod_m[res][level]
            bonus = 100 + (5 * agronomy if res == "food" else 3 * industry)
            rates[res] = (
                base_rate * bonus // 100 * boost // 100 * self.p.speed_pct // 100
            )
        rates["food"] -= self.upkeep(base)
        return rates

    def upkeep(self, base: Base) -> int:
        """Food per hour (milli) for every unit homed at this base."""
        units = self.r.units
        total = 0
        for stacks in (base.garrison, base.away):
            for unit, n in stacks.items():
                total += units[unit].upkeep_m * n
        return total * self.p.speed_pct // 100

    def hourly_value(self, player: Player) -> int:
        """Trade value (milli) of the player's build-resource production/h."""
        total = 0
        for bid in player.base_ids:
            r = self.rates(self.w.bases[bid])
            total += sum(
                r[res] * VALUE_PER_UNIT[res] // MILLI for res in BUILD_RES
            )
        return total

    def _settle(self, base: Base) -> None:
        t = self.w.now_ms
        dt = t - base.settled_ms
        if dt <= 0:
            return
        rates = self.rates(base)
        cap = self.r.cap_m[base.buildings.get("store", 0)]
        for res in RESOURCES:
            rate = rates[res]
            if rate == 0:
                continue
            raw = rate * dt + base.residual[res]
            delta, rem = divmod(raw, HOUR_MS)
            value = base.stock[res] + delta
            if value >= cap and rate > 0:
                base.stock[res] = max(base.stock[res], cap)
                base.residual[res] = 0
            elif value <= 0 and rate < 0:
                base.stock[res] = 0
                base.residual[res] = 0
            else:
                base.stock[res] = value
                base.residual[res] = rem
        base.settled_ms = t

    def _bucket_cap(self, player: Player) -> int:
        return self.p.bucket_hours * self.hourly_value(player)

    def _settle_bucket(self, player: Player) -> None:
        t = self.w.now_ms
        dt = t - player.bucket_ms
        if dt <= 0:
            return
        player.bucket_ms = t
        if player.vacation_state == "active":
            return
        cap = self._bucket_cap(player)
        rate = cap // self.p.bucket_refill_hours
        raw = rate * dt + player.bucket_res
        delta, rem = divmod(raw, HOUR_MS)
        player.bucket_m += delta
        player.bucket_res = rem
        if player.bucket_m >= cap:
            player.bucket_m = cap
            player.bucket_res = 0

    def _before_rate_change(self, player: Player | None, *bases: Base) -> None:
        """Settle bases and the owner's bucket before rates change."""
        if player is not None:
            self._settle_bucket(player)
            for bid in player.base_ids:
                self._settle(self.w.bases[bid])
        for base in bases:
            self._settle(base)

    def _after_rate_change(self, player: Player | None, *bases: Base) -> None:
        """Clamp bucket to the new capacity and re-project starvation."""
        if player is not None:
            cap = self._bucket_cap(player)
            if player.bucket_m > cap:
                player.bucket_m = cap
                player.bucket_res = 0
            for bid in player.base_ids:
                self._project_starvation(self.w.bases[bid])
        for base in bases:
            self._project_starvation(base)

    def _project_starvation(self, base: Base) -> None:
        if base.kind != "player":
            return
        base.rate_version += 1
        net = self.rates(base)["food"]
        if net >= 0:
            return
        to_zero = -(-base.stock["food"] * HOUR_MS // -net)
        self._schedule(
            self.w.now_ms + to_zero + HOUR_MS,
            "starve",
            base.id,
            base.rate_version,
        )

    # ------------------------------------------------------------------
    # setup
    # ------------------------------------------------------------------

    def _place(self, base: Base) -> None:
        self.w.bases[base.id] = base
        self.w.tiles[(base.x, base.y)] = base.id

    def _tile_free(self, x: int, y: int) -> bool:
        if x * x + y * y > self.w.radius * self.w.radius:
            return False
        bid = self.w.tiles.get((x, y))
        return bid is None or self.w.bases[bid].removed

    def ring_tier(self, x: int, y: int) -> int:
        """Camp tier of a tile: 5 at the center, 1 at the edge (§6.12)."""
        d = isqrt(x * x + y * y)
        return max(1, min(5, 5 - 5 * d // (self.w.radius + 1)))

    def add_camp(self, x: int, y: int) -> int:
        """Spawn a full NPC camp of the tile's ring tier."""
        tier = self.ring_tier(x, y)
        ct = self.r.camp_tiers[tier]
        base = Base(
            id=self.w.new_id(),
            owner=None,
            kind="camp",
            x=x,
            y=y,
            tier=tier,
            stock={**dict.fromkeys(RESOURCES, 0), **ct.stock_m},
            settled_ms=self.w.now_ms,
            garrison=dict(ct.garrison),
        )
        self._place(base)
        return base.id

    def join(
        self,
        player_id: int,
        xy: tuple[int, int],
        tutorial_xy: tuple[int, int],
    ) -> Result:
        """Add a player at ``xy`` with a private tutorial camp (§4.3)."""
        w, p = self.w, self.p
        if player_id in w.players:
            return _reject("already_joined")
        if w.now_ms >= (p.join_close_day - 1) * DAY_MS:
            return _reject("joins_closed")
        if not self._tile_free(*xy) or not self._tile_free(*tutorial_xy):
            return _reject("tile_taken")
        round_day = w.now_ms // DAY_MS
        mult = 100 + round_day * 100 // 7
        player = Player(
            id=player_id,
            joined_ms=w.now_ms,
            protection_until=w.now_ms + self._dur(p.protection_hours * HOUR_MS),
            last_seen_ms=w.now_ms,
            bucket_ms=w.now_ms,
        )
        if round_day > 0:
            player.catchup_pct = min(p.catchup_max_pct, round_day * 100 // 7)
            player.catchup_until = w.now_ms + p.catchup_days * DAY_MS
            self._schedule(player.catchup_until, "catchup_end", player_id)
        w.players[player_id] = player
        stock = {r: v * MILLI * mult // 100 for r, v in START_STOCK.items()}
        base = Base(
            id=w.new_id(),
            owner=player_id,
            kind="player",
            x=xy[0],
            y=xy[1],
            tier=self.ring_tier(*xy),
            stock=stock,
            settled_ms=w.now_ms,
            buildings={"quarry": 1, "sawmill": 1, "farm": 1},
        )
        if round_day > 0 and p.headstart_pct > 0:
            self._apply_headstart(player, base)
        self._place(base)
        player.base_ids.append(base.id)
        tut = Base(
            id=w.new_id(),
            owner=player_id,
            kind="tutorial",
            x=tutorial_xy[0],
            y=tutorial_xy[1],
            tier=1,
            stock={
                **dict.fromkeys(RESOURCES, 0),
                **{r: v * MILLI for r, v in TUTORIAL_STOCK.items()},
            },
            settled_ms=w.now_ms,
            garrison={"warden": 1},
        )
        self._place(tut)
        self._schedule(w.now_ms + 72 * HOUR_MS, "tutorial_expire", tut.id)
        player.bucket_m = self._bucket_cap(player)
        self._schedule_inactivity(player)
        return _accept(base_id=base.id, tutorial_id=tut.id)

    def headstart_levels(self) -> dict[str, int]:
        """Building levels at the ``headstart_pct`` percentile (§6.17).

        Taken per building over every active player's first base, then
        clamped so nothing exceeds what the seeded hall allows.
        """
        bases = [
            self.w.bases[pl.base_ids[0]]
            for pl in self.w.players.values()
            if pl.status == "active" and pl.base_ids
        ]
        if not bases:
            return {}
        pct = self.p.headstart_pct
        levels: dict[str, int] = {}
        for building in self.r.buildings:
            values = sorted(b.buildings.get(building, 0) for b in bases)
            levels[building] = values[(len(values) - 1) * pct // 100]
        cap = self.r.hall_cap(levels.get("hall", 0))
        return {
            b: (lv if b == "hall" else min(lv, cap))
            for b, lv in levels.items()
            if lv > 0
        }

    def _apply_headstart(self, player: Player, base: Base) -> None:
        """Seed a late joiner's base; seeded levels count toward power."""
        for building, level in self.headstart_levels().items():
            current = base.buildings.get(building, 0)
            if level <= current:
                continue
            base.buildings[building] = level
            costs = self.r.buildings[building].cost_value_m
            player.spent_value_m += sum(costs[current + 1 : level + 1])

    # ------------------------------------------------------------------
    # common checks
    # ------------------------------------------------------------------

    def _actor(self, player_id: int) -> Player | Result:
        player = self.w.players.get(player_id)
        if player is None:
            return _reject("not_joined")
        if player.status == "gone":
            return _reject("gone")
        if self.w.ended:
            return _reject("round_ended")
        return player

    def touch(self, player_id: int) -> None:
        """Record a session (resets inactivity, §6.11)."""
        player = self.w.players.get(player_id)
        if player is None or player.status == "gone":
            return
        player.last_seen_ms = self.w.now_ms
        if player.status == "inactive":
            player.status = "active"
        self._schedule_inactivity(player)

    def _schedule_inactivity(self, player: Player) -> None:
        player.inactivity_version += 1
        self._schedule(
            player.last_seen_ms + self.p.inactive_hours * HOUR_MS,
            "inactive_check",
            player.id,
            player.inactivity_version,
        )

    def _own_base(self, player: Player, base_id: int) -> Base | Result:
        base = self.w.bases.get(base_id)
        if base is None or base.owner != player.id or base.kind != "player":
            return _reject("not_your_base")
        if player.vacation_state == "active":
            return _reject("on_vacation")
        return base

    def _pay(self, base: Base, cost_m: dict[str, int]) -> bool:
        self._settle(base)
        if any(base.stock.get(r, 0) < v for r, v in cost_m.items()):
            return False
        for r, v in cost_m.items():
            base.stock[r] -= v
        return True

    # ------------------------------------------------------------------
    # build / train / research (§6.2–6.4)
    # ------------------------------------------------------------------

    def planned_level(self, base: Base, building: str) -> int:
        """Level after every queued build of this building completes."""
        queued = [i.amount for i in base.build_queue if i.item == building]
        return max(queued, default=base.buildings.get(building, 0))

    def build(self, player_id: int, base_id: int, building: str) -> Result:
        """Queue the next level of a building."""
        player = self._actor(player_id)
        if isinstance(player, Result):
            return player
        base = self._own_base(player, base_id)
        if isinstance(base, Result):
            return base
        bdef = self.r.buildings.get(building)
        if bdef is None:
            return _reject("unknown_building")
        if len(base.build_queue) >= self.p.build_slots:
            return _reject("lane_full")
        target = self.planned_level(base, building) + 1
        if target > bdef.max_level:
            return _reject("max_level")
        hall = self.planned_level(base, "hall")
        if building != "hall" and target > self.r.hall_cap(hall):
            return _reject("hall_cap")
        for req, lvl in bdef.requires.items():
            if self.planned_level(base, req) < lvl:
                return _reject("requires:" + req)
        cost = bdef.cost_m[target]
        if not self._pay(base, cost):
            return _reject("insufficient")
        start = base.build_queue[-1].end_ms if base.build_queue else self.w.now_ms
        hours_q = bdef.cost_value_m[target]
        ms = hours_q * HOUR_MS // (
            self.p.build_divisor * MILLI * (1 + base.buildings.get("hall", 0))
        )
        item = LaneItem(
            self.w.new_id(),
            "build",
            building,
            target,
            base.id,
            start,
            start + self._dur(ms),
        )
        base.build_queue.append(item)
        self._schedule(item.end_ms, "build_done", base.id, item.id)
        return _accept(item_id=item.id, end_ms=item.end_ms)

    def _ev_build_done(self, base_id: int, item_id: int) -> None:
        base = self.w.bases[base_id]
        if base.removed or not base.build_queue:
            return
        item = base.build_queue[0]
        if item.id != item_id:
            return
        owner = self._owner(base)
        self._before_rate_change(owner, base)
        base.build_queue.pop(0)
        base.buildings[item.item] = item.amount
        if owner is not None:
            cost = self.r.buildings[item.item].cost_value_m[item.amount]
            owner.spent_value_m += cost
        self._after_rate_change(owner, base)

    def train(
        self, player_id: int, base_id: int, unit: str, count: int
    ) -> Result:
        """Queue a training batch at the barracks."""
        player = self._actor(player_id)
        if isinstance(player, Result):
            return player
        base = self._own_base(player, base_id)
        if isinstance(base, Result):
            return base
        udef = self.r.units.get(unit)
        if udef is None or count <= 0:
            return _reject("bad_unit")
        barracks = base.buildings.get("barracks", 0)
        if barracks < self.r.barracks_tier_level[udef.tier]:
            return _reject("barracks_level")
        if len(base.train_queue) >= MAX_TRAIN_BATCHES:
            return _reject("lane_full")
        cost = {r: v * count for r, v in udef.cost_m.items()}
        if not self._pay(base, cost):
            return _reject("insufficient")
        per_unit = udef.train_ms * 100 // (100 + 10 * barracks)
        start = base.train_queue[-1].end_ms if base.train_queue else self.w.now_ms
        item = LaneItem(
            self.w.new_id(),
            "train",
            unit,
            count,
            base.id,
            start,
            start + self._dur(per_unit * count),
        )
        base.train_queue.append(item)
        self._schedule(item.end_ms, "train_done", base.id, item.id)
        return _accept(item_id=item.id, end_ms=item.end_ms)

    def _ev_train_done(self, base_id: int, item_id: int) -> None:
        base = self.w.bases[base_id]
        if base.removed or not base.train_queue:
            return
        item = base.train_queue[0]
        if item.id != item_id:
            return
        owner = self._owner(base)
        self._before_rate_change(owner, base)
        base.train_queue.pop(0)
        base.garrison[item.item] = base.garrison.get(item.item, 0) + item.amount
        self._after_rate_change(owner, base)

    def research(self, player_id: int, base_id: int, tech: str) -> Result:
        """Start the next level of a player-wide research (§6.4)."""
        player = self._actor(player_id)
        if isinstance(player, Result):
            return player
        base = self._own_base(player, base_id)
        if isinstance(base, Result):
            return base
        tdef = self.r.techs.get(tech)
        if tdef is None:
            return _reject("unknown_tech")
        if player.research_item is not None:
            return _reject("lane_full")
        target = player.research.get(tech, 0) + 1
        if target > tdef.max_level:
            return _reject("max_level")
        lab = base.buildings.get("lab", 0)
        if target > lab:
            return _reject("lab_level")
        if not self._pay(base, tdef.cost_m[target]):
            return _reject("insufficient")
        ms = tdef.cost_value_m[target] * HOUR_MS // (MILLI * MILLI * (1 + lab))
        item = LaneItem(
            self.w.new_id(),
            "research",
            tech,
            target,
            base.id,
            self.w.now_ms,
            self.w.now_ms + self._dur(ms),
        )
        player.research_item = item
        self._schedule(item.end_ms, "research_done", player.id, item.id)
        return _accept(item_id=item.id, end_ms=item.end_ms)

    def _ev_research_done(self, player_id: int, item_id: int) -> None:
        player = self.w.players[player_id]
        item = player.research_item
        if item is None or item.id != item_id:
            return
        self._before_rate_change(player)
        player.research[item.item] = item.amount
        player.research_item = None
        player.spent_value_m += self.r.techs[item.item].cost_value_m[
            item.amount
        ]
        self._after_rate_change(player)

    def _ev_catchup_end(self, player_id: int) -> None:
        player = self.w.players[player_id]
        # rates() already ignores the boost at catchup_until; settle with the
        # boost up to now first, then let the new rate apply.
        saved = player.catchup_until
        player.catchup_until = self.w.now_ms + 1
        self._before_rate_change(player)
        player.catchup_until = saved
        self._after_rate_change(player)

    # ------------------------------------------------------------------
    # starvation (§6.5)
    # ------------------------------------------------------------------

    def _ev_starve(self, base_id: int, version: int) -> None:
        base = self.w.bases[base_id]
        if base.removed or base.rate_version != version:
            return
        owner = self._owner(base)
        self._before_rate_change(owner, base)
        net = self.rates(base)["food"]
        if base.stock["food"] > 0 or net >= 0:
            self._after_rate_change(owner, base)
            return
        deficit = -net * 100 // self.p.speed_pct
        locations: list[tuple[str, int, dict[str, int]]] = [
            ("home", base.id, base.garrison)
        ]
        for m in sorted(self.w.marches.values(), key=lambda m: m.id):
            if m.home_base == base.id and m.status != "done":
                locations.append(("march", m.id, m.units))
        stacks = []
        for loc_kind, loc_id, units in locations:
            for unit, n in units.items():
                if n > 0:
                    up = self.r.units[unit].upkeep_m
                    stacks.append((-(n * up), unit, loc_id, loc_kind, units))
        stacks.sort(key=lambda s: (s[0], s[1], s[2]))
        for _w, unit, loc_id, loc_kind, units in stacks:
            if deficit <= 0:
                break
            up = self.r.units[unit].upkeep_m
            remove = min(units[unit], -(-deficit // up))
            units[unit] -= remove
            deficit -= remove * up
            if loc_kind == "march":
                base.away[unit] -= remove
                self._trim_march(self.w.marches[loc_id])
        self._cleanup(base.garrison)
        self._cleanup(base.away)
        self._after_rate_change(owner, base)

    def _trim_march(self, m: March) -> None:
        """Cap cargo to surviving capacity; vanish if no units (§6.5)."""
        self._cleanup(m.units)
        if not m.units:
            m.cargo = {}
            self._finish_march(m, "deserted")
            return
        cap = self._cargo_capacity(m.owner, m.units) * MILLI
        total = sum(m.cargo.values())
        if total <= cap:
            return
        kept = {r: v * cap // total for r, v in m.cargo.items()}
        m.cargo = {r: v for r, v in kept.items() if v}

    @staticmethod
    def _cleanup(units: dict[str, int]) -> None:
        for unit in [u for u, n in units.items() if n <= 0]:
            del units[unit]

    # ------------------------------------------------------------------
    # marches (§6.6)
    # ------------------------------------------------------------------

    def march_slots(self, player: Player) -> int:
        """Concurrent outbound+returning marches allowed."""
        return min(
            8, self.p.march_slots_base + player.research.get("logistics", 0) // 2
        )

    def _active_marches(self, player_id: int) -> list[March]:
        return [
            m
            for m in self.w.marches.values()
            if m.owner == player_id and m.status in ("outbound", "returning")
        ]

    def travel_ms(
        self, player: Player, units: dict[str, int], a: Base, b_xy: tuple
    ) -> int:
        """One-way travel time for the slowest unit (§6.6)."""
        dx, dy = a.x - b_xy[0], a.y - b_xy[1]
        dist_milli = isqrt((dx * dx + dy * dy) * 1_000_000)
        speed = min(self.r.units[u].speed for u in units)
        logistics = player.research.get("logistics", 0)
        ms = -(
            -dist_milli * HOUR_MS * 100
            // (MILLI * speed * (100 + 5 * logistics))
        )
        return self._dur(max(MIN_TRAVEL_MS, ms))

    def _cargo_capacity(self, owner: int, units: dict[str, int]) -> int:
        player = self.w.players.get(owner)
        logistics = player.research.get("logistics", 0) if player else 0
        raw = sum(self.r.units[u].cargo * n for u, n in units.items())
        return raw * (100 + 5 * logistics) // 100

    def affiliated(self, a: int, b: int) -> bool:
        """Shared an alliance now or within the ban window (§6.14)."""
        pa, pb = self.w.players.get(a), self.w.players.get(b)
        if pa is None or pb is None:
            return False
        horizon = self.w.now_ms - self.p.affiliation_ban_days * DAY_MS
        for ma in pa.memberships:
            for mb in pb.memberships:
                if ma.alliance_id != mb.alliance_id:
                    continue
                start = max(ma.joined_ms, mb.joined_ms)
                end = min(
                    ma.left_ms if ma.left_ms is not None else self.w.now_ms,
                    mb.left_ms if mb.left_ms is not None else self.w.now_ms,
                )
                if start <= end and end >= horizon:
                    return True
        return False

    def military(self, player: Player) -> int:
        """Morale size measure: power + all unit value ÷ 1000 (§6.8)."""
        units_value = 0
        for bid in player.base_ids:
            base = self.w.bases[bid]
            for stacks in (base.garrison, base.away):
                for unit, n in stacks.items():
                    units_value += self.r.units[unit].value_m * n
        return player.power + units_value // 1_000_000

    def launch(
        self,
        player_id: int,
        base_id: int,
        mission: str,
        units: dict[str, int],
        *,
        target_base: int | None = None,
        target_xy: tuple[int, int] | None = None,
        cargo: dict[str, int] | None = None,
    ) -> Result:
        """Send units on a mission (§6.6, §6.7, §6.13–6.15)."""
        w = self.w
        player = self._actor(player_id)
        if isinstance(player, Result):
            return player
        home = self._own_base(player, base_id)
        if isinstance(home, Result):
            return home
        if mission not in MISSIONS:
            return _reject("bad_mission")
        units = {u: n for u, n in units.items() if n > 0}
        if not units or any(u not in self.r.units for u in units):
            return _reject("no_units")
        if any(home.garrison.get(u, 0) < n for u, n in units.items()):
            return _reject("units_unavailable")
        if len(self._active_marches(player.id)) >= self.march_slots(player):
            return _reject("no_march_slot")
        target: Base | None = None
        if mission == "settle":
            if target_xy is None or units != {"settler": 1}:
                return _reject("bad_settle")
            if not self._tile_free(*target_xy) or not self._spaced(target_xy):
                return _reject("tile_unavailable")
            slots = 1 + player.research.get("charter", 0)
            if len(player.base_ids) + player.reserved_slots >= slots:
                return _reject("no_base_slot")
            xy = target_xy
        else:
            target = w.bases.get(target_base) if target_base else None
            if target is None or target.removed or target.id == home.id:
                return _reject("bad_target")
            xy = (target.x, target.y)
            check = self._check_target(player, mission, units, target)
            if check is not None:
                return check
        cargo_m: dict[str, int] = {}
        if mission in ("transport", "contribute"):
            cargo_m = {r: v for r, v in (cargo or {}).items() if v > 0}
            if not cargo_m or any(r not in BUILD_RES for r in cargo_m):
                return _reject("bad_cargo")
            if sum(cargo_m.values()) > self._cargo_capacity(
                player.id, units
            ) * MILLI:
                return _reject("cargo_exceeds_capacity")
            if not self._pay(home, cargo_m):
                return _reject("insufficient")
        self._before_rate_change(player, home)
        for u, n in units.items():
            home.garrison[u] -= n
            home.away[u] = home.away.get(u, 0) + n
        self._cleanup(home.garrison)
        travel = self.travel_ms(player, units, home, xy)
        march = March(
            id=w.new_id(),
            owner=player.id,
            home_base=home.id,
            mission=mission,
            units=dict(units),
            cargo=cargo_m,
            target_base=target.id if target else None,
            target_xy=xy,
            depart_ms=w.now_ms,
            arrive_ms=w.now_ms + travel,
        )
        w.marches[march.id] = march
        if mission == "settle":
            player.reserved_slots += 1
        hostile_at_player = (
            mission in HOSTILE
            and target is not None
            and target.owner
            and target.kind == "player"
        )
        if hostile_at_player and target is not None and target.owner:
            player.last_hostile_launch_ms = w.now_ms
            player.attacked[target.owner] = w.now_ms
            if player.protection_until > w.now_ms:
                player.protection_until = w.now_ms
        self._schedule(march.arrive_ms, "arrive", march.id)
        self._after_rate_change(player, home)
        return _accept(march_id=march.id, arrive_ms=march.arrive_ms)

    def _spaced(self, xy: tuple[int, int]) -> bool:
        d = self.p.settle_min_distance
        for b in self.w.bases.values():
            if b.removed or b.kind not in ("player", "site"):
                continue
            if (b.x - xy[0]) ** 2 + (b.y - xy[1]) ** 2 < d * d:
                return False
        return True

    def _check_target(
        self, player: Player, mission: str, units: dict, target: Base
    ) -> Result | None:
        now = self.w.now_ms
        owner = self._owner(target)
        attack_power = sum(self.r.units[u].atk * n for u, n in units.items())
        if mission in ("raid", "attack") and attack_power <= 0:
            return _reject("zero_attack")
        if mission == "scout" and set(units) != {"scout"}:
            return _reject("scouts_only")
        if target.kind == "tutorial" and target.owner != player.id:
            return _reject("private_camp")
        if target.kind == "tutorial" and mission != "raid":
            return _reject("raid_only")
        if mission in HOSTILE:
            if player.vacation_state == "pending":
                return _reject("vacation_pending")
            if target.kind == "site":
                if mission == "raid":
                    return _reject("sites_attack_only")
                site = self.w.sites[target.id]
                if player.alliance_id is None:
                    return _reject("needs_alliance")
                if site.alliance_id == player.alliance_id:
                    return _reject("own_site")
                if site.alliance_id is None and self._holds_site(
                    player.alliance_id
                ):
                    return _reject("already_holds_site")
            if target.kind == "player" and owner is not None:
                if owner.id == player.id:
                    return _reject("own_base")
                if owner.protection_until > now:
                    return _reject("protected_target")
                if owner.vacation_state != "none":
                    return _reject("target_on_vacation")
                if self.affiliated(player.id, owner.id):
                    return _reject("affiliated_target")
            inbound = sum(
                1
                for m in self.w.marches.values()
                if m.owner == player.id
                and m.target_base == target.id
                and m.status == "outbound"
                and m.mission in HOSTILE
            )
            if inbound >= self.p.per_target_cap:
                return _reject("per_target_cap")
            return None
        # friendly missions
        if mission == "contribute":
            site = self.w.sites.get(target.id)
            if site is None or site.alliance_id is None:
                return _reject("not_a_site")
            if site.alliance_id != player.alliance_id:
                return _reject("not_your_site")
            return None
        if mission == "reinforce" and target.kind == "site":
            site = self.w.sites[target.id]
            if site.alliance_id is None or site.alliance_id != player.alliance_id:
                return _reject("not_your_site")
            return None
        if target.kind != "player" or owner is None:
            return _reject("bad_target")
        if owner.id != player.id:
            if player.alliance_id is None or player.alliance_id != owner.alliance_id:
                return _reject("not_ally")
            if mission == "transport" and player.protection_until > now:
                return _reject("protected_sender")
            if mission == "reinforce" and owner.protection_until > now:
                return _reject("protected_host")
        elif mission == "reinforce":
            return _reject("own_base")
        return None

    def recall(self, player_id: int, march_id: int) -> Result:
        """Turn an outbound march around, or bring a detachment home."""
        m = self.w.marches.get(march_id)
        if m is None or m.owner != player_id:
            return _reject("not_your_march")
        if m.status == "outbound":
            elapsed = self.w.now_ms - m.depart_ms
            self._return(m, max(1, elapsed))
            return _accept(return_ms=m.return_ms)
        if m.status == "stationed":
            self._send_home(m)
            return _accept(return_ms=m.return_ms)
        return _reject("not_recallable")

    def dismiss(self, player_id: int, march_id: int) -> Result:
        """Host sends a stationed detachment home."""
        m = self.w.marches.get(march_id)
        if m is None or m.status != "stationed" or m.target_base is None:
            return _reject("not_stationed")
        host = self.w.bases[m.target_base]
        if host.owner != player_id:
            return _reject("not_host")
        self._send_home(m)
        return _accept(return_ms=m.return_ms)

    def _send_home(self, m: March) -> None:
        home = self.w.bases[m.home_base]
        player = self.w.players[m.owner]
        self._return(m, self.travel_ms(player, m.units, home, m.target_xy))

    def _return(self, m: March, travel: int) -> None:
        m.status = "returning"
        m.return_ms = self.w.now_ms + travel
        self._schedule(m.return_ms, "return", m.id)

    def _finish_march(self, m: March, outcome: str) -> None:
        m.status = "done"
        m.outcome = m.outcome or outcome
        if m.mission == "settle":
            owner = self.w.players.get(m.owner)
            if owner is not None and owner.reserved_slots > 0:
                owner.reserved_slots -= 1
        self.w.marches.pop(m.id, None)
        if self.w.keep_marches:
            self.w.finished_marches.append(m)

    def _ev_return(self, march_id: int) -> None:
        m = self.w.marches.get(march_id)
        if m is None or m.status != "returning" or self.w.now_ms < m.return_ms:
            return
        home = self.w.bases[m.home_base]
        owner = self.w.players[m.owner]
        self._before_rate_change(owner, home)
        for u, n in m.units.items():
            home.garrison[u] = home.garrison.get(u, 0) + n
            home.away[u] -= n
        self._cleanup(home.away)
        if not home.removed:
            cap = self.r.cap_m[home.buildings.get("store", 0)]
            for r, v in m.cargo.items():
                home.stock[r] = min(cap, max(home.stock[r], 0) + v)
        self._finish_march(m, "returned")
        self._after_rate_change(owner, home)

    def _ev_arrive(self, march_id: int) -> None:
        m = self.w.marches.get(march_id)
        if m is None or m.status != "outbound":
            return
        if m.mission == "settle":
            self._arrive_settle(m)
            return
        target = self.w.bases.get(m.target_base) if m.target_base else None
        if target is None or target.removed:
            m.outcome = "bounced"
            self._return(m, m.arrive_ms - m.depart_ms)
            return
        handler = {
            "raid": self._arrive_combat,
            "attack": self._arrive_combat,
            "scout": self._arrive_scout,
            "reinforce": self._arrive_reinforce,
            "transport": self._arrive_transport,
            "contribute": self._arrive_contribute,
        }[m.mission]
        handler(m, target)

    # ------------------------------------------------------------------
    # mission resolution
    # ------------------------------------------------------------------

    def _defender_stacks(
        self, target: Base
    ) -> tuple[dict[tuple[int, str], int], list[tuple[int, dict[str, int]]]]:
        """Aggregate defenders by (owner, unit) and list their locations."""
        owner_key = target.owner if target.kind == "player" else 0
        owner_key = owner_key or 0
        stacks: dict[tuple[int, str], int] = {}
        locations: list[tuple[int, dict[str, int]]] = [
            (owner_key, target.garrison)
        ]
        for unit, n in target.garrison.items():
            stacks[(owner_key, unit)] = stacks.get((owner_key, unit), 0) + n
        for m in sorted(self.w.marches.values(), key=lambda m: m.id):
            if m.status == "stationed" and m.target_base == target.id:
                locations.append((m.owner, m.units))
                for unit, n in m.units.items():
                    key = (m.owner, unit)
                    stacks[key] = stacks.get(key, 0) + n
        return stacks, locations

    def _apply_losses(
        self,
        losses: dict[tuple[int, str], int],
        locations: list[tuple[int, dict[str, int]]],
    ) -> None:
        """Split each (owner, unit) loss over that owner's locations."""
        for (owner, unit), lost in losses.items():
            if lost <= 0:
                continue
            holders = [
                units
                for o, units in locations
                if o == owner and units.get(unit, 0) > 0
            ]
            total = sum(h[unit] for h in holders)
            if total <= 0:
                continue
            shares = [h[unit] * lost // total for h in holders]
            extra = lost - sum(shares)
            for i in range(len(holders)):
                if extra <= 0:
                    break
                if shares[i] < holders[i][unit]:
                    shares[i] += 1
                    extra -= 1
            for h, s in zip(holders, shares, strict=True):
                h[unit] -= s

    def _sync_away(self) -> None:
        """Recompute every base's ``away`` from live marches."""
        for base in self.w.bases.values():
            base.away = {}
        for m in self.w.marches.values():
            if m.status == "done":
                continue
            home = self.w.bases[m.home_base]
            for u, n in m.units.items():
                home.away[u] = home.away.get(u, 0) + n

    def _arrive_combat(self, m: March, target: Base) -> None:
        w = self.w
        attacker = w.players[m.owner]
        defender = self._owner(target) if target.kind == "player" else None
        involved = self._involved_bases(m, target)
        for pl, bases in involved:
            self._before_rate_change(pl, *bases)
        raid = m.mission == "raid"
        morale = Q
        if defender is not None:
            revenge = defender.attacked.get(attacker.id, -(10**15))
            if w.now_ms - revenge > DAY_MS:
                morale = combat.morale_q(
                    self.military(attacker), self.military(defender)
                )
        def_stacks, locations = self._defender_stacks(target)
        armor = {
            o: w.players[o].research.get("armor", 0)
            for o, _u in def_stacks
            if o in w.players
        }
        att_stacks = {(attacker.id, u): n for u, n in m.units.items()}
        wall = target.buildings.get("wall", 0) if target.kind == "player" else 0
        result = combat.resolve_battle(
            att_stacks,
            def_stacks,
            self._stats,
            arms_level=attacker.research.get("arms", 0),
            armor_by_owner=armor,
            wall=wall,
            morale_q=morale,
            raid=raid,
        )
        units = self.r.units
        att_value = sum(units[u].value_m * n for u, n in m.units.items())
        att_lost_value = 0
        for (_o, unit), lost in result.att_losses.items():
            m.units[unit] -= lost
            att_lost_value += units[unit].value_m * lost
        self._apply_losses(result.def_losses, locations)
        self._cleanup(target.garrison)
        for dm in list(w.marches.values()):
            if dm.status == "stationed" and dm.target_base == target.id:
                self._cleanup(dm.units)
                if not dm.units:
                    self._finish_march(dm, "destroyed")
        loot_value = 0
        if result.attacker_won:
            loot_value = self._take_loot(m, target, attacker, defender)
            if not raid:
                self._siege(m, target, attacker)
        self._cleanup(m.units)
        self._sync_away()
        if target.kind in ("camp", "tutorial") and target.full:
            target.full = False
            if target.kind == "camp":
                self._schedule(
                    w.now_ms + self.p.camp_respawn_hours * HOUR_MS,
                    "camp_respawn",
                    target.id,
                )
        if target.kind == "tutorial":
            if result.attacker_won:
                target.removed = True
            else:
                self._schedule(w.now_ms + HOUR_MS, "tutorial_respawn", target.id)
        if w.keep_reports:
            w.reports.append(
                {
                    "kind": m.mission,
                    "t_ms": w.now_ms,
                    "attacker": attacker.id,
                    "defender": target.owner or 0,
                    "base": target.id,
                    "x": target.x,
                    "y": target.y,
                    "attacker_won": result.attacker_won,
                    "A": result.A,
                    "D": result.D,
                    "morale_q": morale,
                    "loot_value_m": loot_value,
                    "att_value_m": att_value,
                    "att_lost_value_m": att_lost_value,
                }
            )
        m.outcome = "won" if result.attacker_won else "lost"
        if m.units:
            self._return(m, m.arrive_ms - m.depart_ms)
        else:
            self._finish_march(m, m.outcome)
        for pl, bases in involved:
            self._after_rate_change(pl, *bases)

    def _involved_bases(
        self, m: March, target: Base
    ) -> list[tuple[Player | None, list[Base]]]:
        """Owners whose rates can change in a battle (homes of all units)."""
        owners: dict[int | None, set[int]] = {m.owner: {m.home_base}}
        if target.kind == "player":
            owners.setdefault(target.owner, set()).add(target.id)
        for dm in self.w.marches.values():
            if dm.status == "stationed" and dm.target_base == target.id:
                owners.setdefault(dm.owner, set()).add(dm.home_base)
        out = []
        for owner, bids in owners.items():
            player = self.w.players.get(owner) if owner else None
            out.append((player, [self.w.bases[b] for b in sorted(bids)]))
        return out

    def _take_loot(
        self, m: March, target: Base, attacker: Player, defender: Player | None
    ) -> int:
        if target.kind == "site":
            return 0
        if target.kind == "player":
            self._settle(target)
        vault = (
            self.r.vault_m[target.buildings.get("store", 0)]
            if target.kind == "player"
            else 0
        )
        exposed = {
            r: max(0, target.stock[r] - vault) * self.p.loot_pct // 100
            for r in BUILD_RES
        }
        bucket = None
        if defender is not None:
            self._settle_bucket(defender)
            bucket = defender.bucket_m
        taken = combat.allocate_loot(
            exposed,
            self._cargo_capacity(attacker.id, m.units),
            bucket,
            VALUE_PER_UNIT,
        )
        for r, v in taken.items():
            target.stock[r] -= v
            m.cargo[r] = m.cargo.get(r, 0) + v
        loot_value = value_m(taken)
        if defender is not None:
            defender.bucket_m -= loot_value
            self.w.loot_log.append(
                LootEntry(
                    self.w.now_ms,
                    defender.id,
                    attacker.id,
                    loot_value,
                    self.hourly_value(defender),
                )
            )
        return loot_value

    def _siege(self, m: March, target: Base, attacker: Player) -> None:
        """After a won attack: rams hit walls; sites are captured/sieged."""
        rams = m.units.pop("ram", 0)
        siege_value = rams * self.r.units["ram"].value_m
        if target.kind == "site":
            self._site_attacked(target, attacker, siege_value)
        elif target.kind == "player" and rams > 0:
            level = target.buildings.get("wall", 0)
            costs = list(self.r.buildings["wall"].cost_value_m[1 : level + 1])
            removed = combat.siege_levels(siege_value, costs, level, 3)
            if removed:
                target.buildings["wall"] = level - removed

    def _arrive_scout(self, m: March, target: Base) -> None:
        attacker = self.w.players[m.owner]
        defender = self._owner(target)
        att = m.units.get("scout", 0)
        dsc = target.garrison.get("scout", 0)
        esp_a = attacker.research.get("espionage", 0)
        esp_d = defender.research.get("espionage", 0) if defender else 0
        ok, att_lost, def_lost = combat.resolve_scout(att, dsc, esp_a, esp_d)
        m.units["scout"] = att - att_lost
        if def_lost:
            target.garrison["scout"] = dsc - def_lost
        self._cleanup(m.units)
        self._cleanup(target.garrison)
        self._sync_away()
        m.outcome = "won" if ok else "lost"
        if self.w.keep_reports:
            self.w.reports.append(
                {
                    "kind": "scout",
                    "t_ms": self.w.now_ms,
                    "attacker": attacker.id,
                    "defender": target.owner or 0,
                    "base": target.id,
                    "x": target.x,
                    "y": target.y,
                    "attacker_won": ok,
                    "seen": (
                        {"stock": dict(target.stock),
                         "garrison": dict(target.garrison)}
                        if ok
                        else None
                    ),
                }
            )
        if m.units:
            self._return(m, m.arrive_ms - m.depart_ms)
        else:
            self._finish_march(m, m.outcome)

    def _arrive_reinforce(self, m: March, target: Base) -> None:
        owner = self.w.players[m.owner]
        if target.kind == "site":
            site = self.w.sites[target.id]
            ok = site.alliance_id is not None and site.alliance_id == owner.alliance_id
        else:
            host = self._owner(target)
            ok = (
                host is not None
                and owner.alliance_id is not None
                and host.alliance_id == owner.alliance_id
                and host.vacation_state != "active"
            )
        if not ok:
            m.outcome = "bounced"
            self._return(m, m.arrive_ms - m.depart_ms)
            return
        m.status = "stationed"
        m.outcome = "stationed"

    def _arrive_transport(self, m: March, target: Base) -> None:
        owner = self.w.players[m.owner]
        host = self._owner(target)
        ok = host is not None and (
            host.id == owner.id
            or (
                owner.alliance_id is not None
                and host.alliance_id == owner.alliance_id
            )
        )
        if ok and host is not None:
            self._settle(target)
            cap = self.r.cap_m[target.buildings.get("store", 0)]
            for r in list(m.cargo):
                room = max(0, cap - target.stock[r])
                give = min(room, m.cargo[r])
                target.stock[r] += give
                m.cargo[r] -= give
            m.cargo = {r: v for r, v in m.cargo.items() if v}
            m.outcome = "delivered"
        else:
            m.outcome = "bounced"
        self._return(m, m.arrive_ms - m.depart_ms)

    def _arrive_settle(self, m: March) -> None:
        w = self.w
        player = w.players[m.owner]
        xy = m.target_xy
        if not (self._tile_free(*xy) and self._spaced(xy)):
            m.outcome = "bounced"
            self._return(m, m.arrive_ms - m.depart_ms)
            return
        home = w.bases[m.home_base]
        self._before_rate_change(player, home)
        home.away["settler"] -= 1
        self._cleanup(home.away)
        base = Base(
            id=w.new_id(),
            owner=player.id,
            kind="player",
            x=xy[0],
            y=xy[1],
            tier=self.ring_tier(*xy),
            stock={
                **{r: NEW_BASE_STOCK * MILLI for r in BUILD_RES},
                "food": NEW_BASE_STOCK * MILLI,
            },
            settled_ms=w.now_ms,
            buildings={"quarry": 1, "sawmill": 1, "farm": 1},
        )
        self._place(base)
        player.base_ids.append(base.id)
        m.units = {}
        self._finish_march(m, "settled")
        self._after_rate_change(player, home, base)

    # ------------------------------------------------------------------
    # camps, tutorial (§6.12)
    # ------------------------------------------------------------------

    def _ev_camp_respawn(self, base_id: int) -> None:
        base = self.w.bases[base_id]
        if base.removed or base.kind != "camp":
            return
        ct = self.r.camp_tiers[base.tier]
        base.stock = {**dict.fromkeys(RESOURCES, 0), **ct.stock_m}
        base.garrison = dict(ct.garrison)
        base.full = True

    def _ev_tutorial_respawn(self, base_id: int) -> None:
        base = self.w.bases[base_id]
        if base.removed:
            return
        base.garrison = {"warden": 1}
        base.stock = {
            **dict.fromkeys(RESOURCES, 0),
            **{r: v * MILLI for r, v in TUTORIAL_STOCK.items()},
        }
        base.full = True

    def _ev_tutorial_expire(self, base_id: int) -> None:
        self.w.bases[base_id].removed = True

    def _ev_daily(self) -> None:
        """Rebalance converted camps against the world budget."""
        w = self.w
        active = sum(1 for p in w.players.values() if p.status != "gone")
        budget = -(-active * self.p.camps_per_player_x10 // 10)
        camps = [b for b in w.bases.values() if b.kind == "camp" and not b.removed]
        excess = len(camps) - budget
        converted = sorted(
            (b for b in camps if b.converted_ms is not None),
            key=lambda b: (b.converted_ms, b.id),
        )
        for base in converted:
            if excess <= 0:
                break
            base.removed = True
            excess -= 1

    # ------------------------------------------------------------------
    # inactivity (§6.11)
    # ------------------------------------------------------------------

    def _ev_inactive_check(self, player_id: int, version: int) -> None:
        player = self.w.players[player_id]
        if player.inactivity_version != version or player.status == "gone":
            return
        idle = self.w.now_ms - player.last_seen_ms
        if idle >= self.p.gone_days * DAY_MS:
            self._make_gone(player)
            return
        if idle >= self.p.inactive_hours * HOUR_MS:
            player.status = "inactive"
        self._schedule(
            player.last_seen_ms + self.p.gone_days * DAY_MS,
            "inactive_check",
            player.id,
            version,
        )

    def _make_gone(self, player: Player) -> None:
        w = self.w
        self._before_rate_change(player)
        player.status = "gone"
        for m in list(w.marches.values()):
            if m.owner == player.id:
                m.units = {}
                m.cargo = {}
                self._finish_march(m, "disbanded")
            elif (
                m.status == "stationed"
                and m.target_base in player.base_ids
            ):
                self._send_home(m)
        if player.alliance_id is not None:
            self._leave_alliance(player)
        for bid in player.base_ids:
            base = w.bases[bid]
            tier = self.ring_tier(base.x, base.y)
            ct = self.r.camp_tiers[tier]
            base.owner = None
            base.kind = "camp"
            base.tier = tier
            base.stock = {**dict.fromkeys(RESOURCES, 0), **ct.stock_m}
            base.garrison = dict(ct.garrison)
            base.build_queue = []
            base.train_queue = []
            base.full = True
            base.converted_ms = w.now_ms
        player.research_item = None
        self._sync_away()

    # ------------------------------------------------------------------
    # vacation (§6.11)
    # ------------------------------------------------------------------

    def request_vacation(self, player_id: int) -> Result:
        """none → pending (12 h), if allowed."""
        player = self._actor(player_id)
        if isinstance(player, Result):
            return player
        p, now = self.p, self.w.now_ms
        if player.vacation_state != "none":
            return _reject("vacation_busy")
        if now < player.vacation_cooldown_until:
            return _reject("vacation_cooldown")
        if now - player.last_hostile_launch_ms < p.vacation_delay_hours * HOUR_MS:
            return _reject("recent_hostility")
        if player.vacation_used_ms >= p.vacation_quota_days * DAY_MS:
            return _reject("vacation_quota")
        player.vacation_state = "pending"
        player.vacation_at = now + p.vacation_delay_hours * HOUR_MS
        self._schedule(player.vacation_at, "vacation_activate", player.id)
        return _accept(activates_ms=player.vacation_at)

    def cancel_vacation(self, player_id: int) -> Result:
        """pending → none."""
        player = self.w.players.get(player_id)
        if player is None or player.vacation_state != "pending":
            return _reject("not_pending")
        player.vacation_state = "none"
        player.vacation_cooldown_until = (
            self.w.now_ms + self.p.vacation_cooldown_hours * HOUR_MS
        )
        return _accept()

    def _ev_vacation_activate(self, player_id: int) -> None:
        w = self.w
        player = w.players[player_id]
        if player.vacation_state != "pending" or w.now_ms < player.vacation_at:
            return
        self._before_rate_change(player)
        player.vacation_state = "active"
        player.vacation_at = w.now_ms
        for m in list(w.marches.values()):
            if m.owner == player.id and m.status == "outbound":
                self._return(m, max(1, w.now_ms - m.depart_ms))
            elif m.status == "stationed" and m.target_base in player.base_ids:
                self._send_home(m)
        left = self.p.vacation_quota_days * DAY_MS - player.vacation_used_ms
        self._schedule(w.now_ms + left, "vacation_quota_end", player.id)
        self._after_rate_change(player)

    def exit_vacation(self, player_id: int) -> Result:
        """active → none after the minimum stay."""
        player = self.w.players.get(player_id)
        if player is None or player.vacation_state != "active":
            return _reject("not_on_vacation")
        if self.w.now_ms - player.vacation_at < self.p.vacation_min_hours * HOUR_MS:
            return _reject("vacation_minimum")
        self._end_vacation(player)
        return _accept()

    def _ev_vacation_quota_end(self, player_id: int) -> None:
        player = self.w.players[player_id]
        if player.vacation_state == "active":
            self._end_vacation(player)

    def _end_vacation(self, player: Player) -> None:
        now = self.w.now_ms
        player.vacation_used_ms += now - player.vacation_at
        for bid in player.base_ids:
            self.w.bases[bid].settled_ms = now  # nothing accrued on vacation
        player.bucket_ms = now
        player.vacation_state = "none"
        player.vacation_cooldown_until = (
            now + self.p.vacation_cooldown_hours * HOUR_MS
        )
        self._after_rate_change(player)

    # ------------------------------------------------------------------
    # alliances (§6.14)
    # ------------------------------------------------------------------

    def create_alliance(self, player_id: int, name: str, tag: str) -> Result:
        """Found an alliance with the player as leader."""
        player = self._actor(player_id)
        if isinstance(player, Result):
            return player
        if player.alliance_id is not None:
            return _reject("already_member")
        if self.w.now_ms < player.hop_cooldown_until:
            return _reject("hop_cooldown")
        if any(a.tag == tag for a in self.w.alliances.values()):
            return _reject("tag_taken")
        alliance = Alliance(self.w.new_id(), name, tag, leader=player.id)
        self.w.alliances[alliance.id] = alliance
        self._add_member(alliance, player)
        return _accept(alliance_id=alliance.id)

    def invite(self, player_id: int, target_id: int) -> Result:
        """Leader/officer invites a player."""
        player = self._actor(player_id)
        if isinstance(player, Result):
            return player
        alliance = self.w.alliances.get(player.alliance_id or 0)
        target = self.w.players.get(target_id)
        if alliance is None or target is None:
            return _reject("bad_invite")
        if player.id != alliance.leader and player.id not in alliance.officers:
            return _reject("not_officer")
        target.invites.add(alliance.id)
        return _accept()

    def accept_invite(self, player_id: int, alliance_id: int) -> Result:
        """Join an alliance that invited you."""
        player = self._actor(player_id)
        if isinstance(player, Result):
            return player
        alliance = self.w.alliances.get(alliance_id)
        if alliance is None or alliance_id not in player.invites:
            return _reject("no_invite")
        if player.alliance_id is not None:
            return _reject("already_member")
        if self.w.now_ms < player.hop_cooldown_until:
            return _reject("hop_cooldown")
        if len(alliance.members) >= self.p.alliance_cap:
            return _reject("alliance_full")
        player.invites.discard(alliance_id)
        self._add_member(alliance, player)
        return _accept()

    def leave_alliance(self, player_id: int) -> Result:
        """Leave your alliance (leader leaving disbands it if alone)."""
        player = self.w.players.get(player_id)
        if player is None or player.alliance_id is None:
            return _reject("not_member")
        self._leave_alliance(player)
        return _accept()

    def kick(self, player_id: int, target_id: int) -> Result:
        """Leader/officer removes a member."""
        player = self.w.players.get(player_id)
        target = self.w.players.get(target_id)
        if player is None or target is None or player.alliance_id is None:
            return _reject("bad_kick")
        alliance = self.w.alliances[player.alliance_id]
        if target.alliance_id != alliance.id or target.id == alliance.leader:
            return _reject("bad_kick")
        if player.id != alliance.leader and player.id not in alliance.officers:
            return _reject("not_officer")
        self._leave_alliance(target)
        return _accept()

    def promote(self, player_id: int, target_id: int) -> Result:
        """Leader makes a member an officer."""
        player = self.w.players.get(player_id)
        if player is None or player.alliance_id is None:
            return _reject("not_member")
        alliance = self.w.alliances[player.alliance_id]
        if player.id != alliance.leader or target_id not in alliance.members:
            return _reject("not_leader")
        alliance.officers.add(target_id)
        return _accept()

    def _add_member(self, alliance: Alliance, player: Player) -> None:
        alliance.members.add(player.id)
        player.alliance_id = alliance.id
        player.memberships.append(Membership(alliance.id, self.w.now_ms))

    def _leave_alliance(self, player: Player) -> None:
        w = self.w
        alliance = w.alliances[player.alliance_id or 0]
        alliance.members.discard(player.id)
        alliance.officers.discard(player.id)
        player.memberships[-1].left_ms = w.now_ms
        player.alliance_id = None
        player.hop_cooldown_until = w.now_ms + self.p.alliance_hop_hours * HOUR_MS
        for m in list(w.marches.values()):
            if m.status != "stationed" or m.target_base is None:
                continue
            host = w.bases[m.target_base]
            mine_abroad = m.owner == player.id and host.owner != player.id
            guest_here = host.owner == player.id and m.owner != player.id
            if mine_abroad or guest_here:
                self._send_home(m)
        if alliance.leader == player.id and alliance.members:
            alliance.leader = min(alliance.members)

    # ------------------------------------------------------------------
    # monument (§6.15)
    # ------------------------------------------------------------------

    def _ev_qualify(self) -> None:
        count = 0
        for alliance in self.w.alliances.values():
            active = sum(
                1
                for pid in alliance.members
                if self.w.players[pid].status == "active"
            )
            if active >= self.p.site_qualify_members:
                count += 1
        self.w.qualified_alliances = count

    def _ev_spawn_sites(self) -> None:
        """Place one site per two qualified alliances near the center."""
        n = -(-self.w.qualified_alliances // 2)
        ring = max(2, self.w.radius // 8)
        r = self.w.radius
        candidates = sorted(
            (
                (abs(isqrt(x * x + y * y) - ring), x, y)
                for x in range(-r, r + 1)
                for y in range(-r, r + 1)
            ),
        )
        spots: list[tuple[int, int]] = []
        for _d, x, y in candidates:
            if len(spots) >= n:
                break
            if not self._tile_free(x, y):
                continue
            if any((x - a) ** 2 + (y - b) ** 2 < 9 for a, b in spots):
                continue
            spots.append((x, y))
        for x, y in spots:
            base = Base(
                id=self.w.new_id(),
                owner=None,
                kind="site",
                x=x,
                y=y,
                tier=6,
                stock=dict.fromkeys(RESOURCES, 0),
                settled_ms=self.w.now_ms,
                garrison=dict(SITE_GARRISON),
            )
            self._place(base)
            self.w.sites[base.id] = Site(base.id)

    def _holds_site(self, alliance_id: int | None) -> bool:
        return alliance_id is not None and any(
            s.alliance_id == alliance_id for s in self.w.sites.values()
        )

    def _site_attacked(
        self, target: Base, attacker: Player, siege_value: int
    ) -> None:
        """Won attack on a site: capture or siege (§6.15 state machine)."""
        site = self.w.sites[target.id]
        costs = list(self.r.monument_cost_value_m[1:])
        half = siege_value // 2
        was_building = site.state == "building"
        if not self._holds_site(attacker.alliance_id):
            if site.alliance_id is not None and site.level > 0:
                site.level -= 1
                site.level -= combat.siege_levels(half, costs, site.level, 1)
            site.alliance_id = attacker.alliance_id
            site.contributed = {"ore": 0, "wood": 0, "gem": 0}
        elif site.alliance_id is not None:
            site.level -= combat.siege_levels(half, costs, site.level, 1)
            if was_building:
                site.contributed = {"ore": 0, "wood": 0, "gem": 0}
        else:
            return  # npc site hit by an alliance that already holds one
        site.state = "owned"
        site.build_end_ms = 0
        site.hold_until = 0
        site.version += 1
        self._maybe_fund(site)

    def _arrive_contribute(self, m: March, target: Base) -> None:
        owner = self.w.players[m.owner]
        site = self.w.sites.get(target.id)
        if (
            site is None
            or site.alliance_id is None
            or site.alliance_id != owner.alliance_id
            or site.level >= self.p.monument_levels
        ):
            m.outcome = "bounced"
            self._return(m, m.arrive_ms - m.depart_ms)
            return
        need = self.r.monument_recipe_m[site.level + 1]
        if site.state != "building":
            for r in BUILD_RES:
                room = max(0, need[r] - site.contributed[r])
                give = min(room, m.cargo.get(r, 0))
                site.contributed[r] += give
                if give:
                    m.cargo[r] -= give
        m.cargo = {r: v for r, v in m.cargo.items() if v}
        m.outcome = "delivered"
        self._maybe_fund(site)
        self._return(m, m.arrive_ms - m.depart_ms)

    def _maybe_fund(self, site: Site) -> None:
        if site.state == "building" or site.level >= self.p.monument_levels:
            return
        need = self.r.monument_recipe_m[site.level + 1]
        if all(site.contributed[r] >= need[r] for r in BUILD_RES):
            site.state = "building"
            site.build_end_ms = self.w.now_ms + self._dur(
                self.p.monument_build_hours * HOUR_MS
            )
            self._schedule(
                site.build_end_ms, "site_built", site.base_id, site.version
            )

    def _ev_site_built(self, base_id: int, version: int) -> None:
        site = self.w.sites[base_id]
        if site.version != version or site.state != "building":
            return
        site.level += 1
        site.state = "owned"
        site.level_reached_ms = self.w.now_ms
        site.contributed = {"ore": 0, "wood": 0, "gem": 0}
        site.version += 1
        if site.level >= self.p.monument_levels:
            site.hold_until = self.w.now_ms + self._dur(
                self.p.monument_hold_hours * HOUR_MS
            )
            self._schedule(site.hold_until, "site_hold", base_id, site.version)
        else:
            self._maybe_fund(site)

    def _ev_site_hold(self, base_id: int, version: int) -> None:
        site = self.w.sites[base_id]
        if site.version != version or site.level < self.p.monument_levels:
            return
        self.w.winner_alliance = site.alliance_id
        self._end_round()

    def _end_round(self) -> None:
        w = self.w
        if w.ended:
            return
        if w.winner_alliance is None and w.sites:
            best = sorted(
                (s for s in w.sites.values() if s.alliance_id is not None),
                key=lambda s: (-s.level, s.level_reached_ms, s.base_id),
            )
            if best and best[0].level > 0:
                w.winner_alliance = best[0].alliance_id
        for player in w.players.values():
            self._settle_bucket(player)
            for bid in player.base_ids:
                self._settle(w.bases[bid])
        w.ended = True
