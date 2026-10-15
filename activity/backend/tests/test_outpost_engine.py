"""Outpost engine behaviour tests (Phase 0).

Covers the ten acceptance criteria:
  1  Production: stock after N hours matches table rate; residual correctness;
                 store cap clamps
  2  Build lane: 2-slot limit, hall cap, prerequisites, sequential end times,
                 cost deducted, power increases on completion
  3  Starvation: desertion clock, picks largest upkeep-weighted stack across
                 home AND marching units, march with no units vanishes, cargo trim
  4  Loot bucket P2: 12-h window loss ≤ 8h production, vault protects, food
                 never looted
  5  Protection / morale / affiliation guards
  6  Vacation state machine
  7  Settle: slot reserved at launch; second settler rejected; tile-taken bounce
  8  Monument: qualify gate, capture, contributions fund a level, hold wins
  9  Round-end barrier
 10 Determinism: identical action scripts → identical final state

Run from activity/backend:
  ../../.venv/bin/python -m pytest -q tests/test_outpost_engine.py
"""

import dataclasses
import hashlib
import json

from app.outpost.engine.core import Engine
from app.outpost.engine.state import World
from app.outpost.rules.model import (
    DAY_MS,
    HOUR_MS,
    MILLI,
    Params,
    cached,
)

# ---------------------------------------------------------------------------
# World-building helpers
# ---------------------------------------------------------------------------

_BASE_PARAMS = Params(
    speed_pct=100,
    inactive_hours=72 * 24,  # 72 days – never fires in our tests
    gone_days=100,  # never fires in our tests
)


def _world(params: Params = _BASE_PARAMS, *, radius: int = 26) -> World:
    return World(
        rules=cached(params),
        radius=radius,
        end_ms=28 * DAY_MS,
    )


def _engine(params: Params = _BASE_PARAMS, *, radius: int = 26) -> Engine:
    w = _world(params, radius=radius)
    e = Engine(w)
    e.start()
    return e


def _setup_player(
    engine: Engine,
    player_id: int = 1,
    xy: tuple[int, int] = (5, 0),
    tutorial_xy: tuple[int, int] = (7, 0),
) -> int:
    """Join a player and return their first base id."""
    r = engine.join(player_id, xy, tutorial_xy)
    assert r.ok, r.code
    return r.data["base_id"]


def _give_stock(base, **res_units: int) -> None:
    """Add stock in whole units (auto-converts to milli)."""
    for r, v in res_units.items():
        base.stock[r] = base.stock.get(r, 0) + v * MILLI


def _set_stock(base, **res_units: int) -> None:
    """Set stock in whole units."""
    for r, v in res_units.items():
        base.stock[r] = v * MILLI


def _settle(engine: Engine, base) -> None:
    """Force-settle a base (production is lazy; call to materialise stock)."""
    engine._settle(base)



def _clear_protection(engine: Engine, *player_ids: int) -> None:
    """Set protection_until to 0 for given players (or all players)."""
    targets = player_ids if player_ids else list(engine.w.players)
    for pid in targets:
        p = engine.w.players.get(pid)
        if p is not None:
            p.protection_until = 0

def _force_rate_update(engine: Engine, player_id: int) -> None:
    """Settle bucket and re-project starvation after manual garrison changes."""
    player = engine.w.players[player_id]
    engine._before_rate_change(player, *[engine.w.bases[b] for b in player.base_ids])
    engine._after_rate_change(player, *[engine.w.bases[b] for b in player.base_ids])


# ---------------------------------------------------------------------------
# 1. Production
# ---------------------------------------------------------------------------


class TestProduction:
    """§6.2 prod rate, residual correctness (§7.6), store cap clamp."""

    def test_rate_matches_table_after_n_hours(self) -> None:
        """Stock after N hours equals prod_m × N (residual zero on exact hours)."""
        e = _engine()
        bid = _setup_player(e)
        base = e.w.bases[bid]
        # zero stock so cap never interferes
        base.stock = dict.fromkeys(base.stock, 0)
        base.residual = dict.fromkeys(base.residual, 0)

        rules = e.w.rules
        hours = 3
        # expected = rate × 3h (rate already speed-adjusted)
        expected_ore = rules.prod_m["ore"][base.buildings.get("quarry", 0)] * hours
        expected_wood = rules.prod_m["wood"][base.buildings.get("sawmill", 0)] * hours

        e.advance(hours * HOUR_MS)
        _settle(e, base)

        assert base.stock["ore"] == expected_ore, (
            f"ore: got {base.stock['ore']}, expected {expected_ore}"
        )
        assert base.stock["wood"] == expected_wood, (
            f"wood: got {base.stock['wood']}, expected {expected_wood}"
        )
        # residual must be zero on exact-hour boundary
        assert base.residual["ore"] == 0
        assert base.residual["wood"] == 0

    def test_residual_correctness_small_steps_equal_one_big(self) -> None:
        """Advancing in 1-min steps yields the same stock as one 6-h advance."""

        def _run(step_ms: int) -> dict[str, int]:
            e = _engine()
            bid = _setup_player(e)
            base = e.w.bases[bid]
            base.stock = dict.fromkeys(base.stock, 0)
            base.residual = dict.fromkeys(base.residual, 0)
            target = 6 * HOUR_MS
            t = 0
            while t < target:
                t = min(t + step_ms, target)
                e.advance(t)
            _settle(e, base)
            return dict(base.stock)

        one_shot = _run(6 * HOUR_MS)
        small = _run(60_000)  # 1-minute steps
        assert one_shot == small

    def test_store_cap_clamps_stock(self) -> None:
        """Stock never exceeds the store cap after production."""
        e = _engine()
        bid = _setup_player(e)
        base = e.w.bases[bid]
        cap = e.w.rules.cap_m[0]  # store level 0
        base.stock["ore"] = cap - 1
        base.residual["ore"] = 0

        e.advance(10 * HOUR_MS)
        _settle(e, base)
        assert base.stock["ore"] <= cap


# ---------------------------------------------------------------------------
# 2. Build lane
# ---------------------------------------------------------------------------


class TestBuildLane:
    """§6.2 queue rules, hall cap, prerequisites."""

    def test_two_slot_limit(self) -> None:
        """Third build while two already queued → lane_full."""
        e = _engine()
        bid = _setup_player(e)
        base = e.w.bases[bid]
        _give_stock(base, ore=100_000, wood=100_000, gem=100_000)

        r1 = e.build(1, bid, "quarry")
        assert r1.ok
        r2 = e.build(1, bid, "sawmill")
        assert r2.ok
        r3 = e.build(1, bid, "farm")
        assert not r3.ok
        assert r3.code == "lane_full"

    def test_hall_cap(self) -> None:
        """Non-hall building can't be queued past 2*hall+5."""
        e = _engine()
        bid = _setup_player(e)
        base = e.w.bases[bid]
        _give_stock(base, ore=10_000_000, wood=10_000_000, gem=10_000_000)

        # hall=0 → cap=5; quarry starts at 1, so we can build to 5 (4 more levels)
        for _ in range(4):
            r = e.build(1, bid, "quarry")
            assert r.ok, r.code
            e.advance(r.data["end_ms"])
        # quarry now at 5; next is 6 > cap(hall=0)=5
        r = e.build(1, bid, "quarry")
        assert not r.ok
        assert r.code == "hall_cap"

    def test_prerequisites_enforced(self) -> None:
        """gemworks requires hall 1; rejected without it."""
        e = _engine()
        bid = _setup_player(e)
        base = e.w.bases[bid]
        _give_stock(base, ore=100_000, wood=100_000, gem=100_000)
        assert base.buildings.get("hall", 0) == 0
        r = e.build(1, bid, "gemworks")
        assert not r.ok
        assert "hall" in r.code

    def test_sequential_end_times(self) -> None:
        """Second queued item starts at the first item's end_ms."""
        e = _engine()
        bid = _setup_player(e)
        base = e.w.bases[bid]
        _give_stock(base, ore=100_000, wood=100_000, gem=100_000)

        r1 = e.build(1, bid, "quarry")
        r2 = e.build(1, bid, "sawmill")
        assert r1.ok and r2.ok
        item1 = base.build_queue[0]
        item2 = base.build_queue[1]
        assert item2.start_ms == item1.end_ms

    def test_cost_deducted_immediately(self) -> None:
        """Cost is deducted from stock when the build is queued."""
        e = _engine()
        bid = _setup_player(e)
        base = e.w.bases[bid]
        _give_stock(base, ore=1_000_000, wood=1_000_000)
        rules = e.w.rules
        cost = rules.buildings["quarry"].cost_m[2]  # quarry L1 → L2
        ore_before = base.stock["ore"]

        r = e.build(1, bid, "quarry")
        assert r.ok
        assert base.stock["ore"] == ore_before - cost.get("ore", 0)

    def test_spent_value_increases_after_build_done(self) -> None:
        """player.spent_value_m grows after build completion."""
        e = _engine()
        bid = _setup_player(e)
        base = e.w.bases[bid]
        _give_stock(base, ore=1_000_000, wood=1_000_000)
        spent_before = e.w.players[1].spent_value_m

        r = e.build(1, bid, "quarry")
        assert r.ok
        e.advance(r.data["end_ms"])
        assert base.buildings["quarry"] == 2
        assert e.w.players[1].spent_value_m > spent_before


# ---------------------------------------------------------------------------
# 3. Starvation (§6.5)
# ---------------------------------------------------------------------------


class TestStarvation:
    """Desertion clock, picks right stacks, march vanishes, cargo trim."""

    def _starvation_base(
        self, brutes: int = 50, extra_params: dict | None = None
    ) -> tuple[Engine, int]:
        """Engine with player 1 having zero farm and given brute count."""
        kw = dict(extra_params or {})
        params = _BASE_PARAMS.with_changes(**kw)
        e = _engine(params)
        bid = _setup_player(e, 1, (5, 0), (7, 0))
        base = e.w.bases[bid]
        base.buildings.pop("farm", None)
        base.stock["food"] = 0
        base.residual["food"] = 0
        base.garrison = {"brute": brutes}
        base.away = {}
        _force_rate_update(e, 1)
        return e, bid

    def test_units_desert_when_starving(self) -> None:
        """After food hits 0 with deficit, units desert within a few hours."""
        e, bid = self._starvation_base(brutes=50)
        base = e.w.bases[bid]
        initial_brutes = base.garrison.get("brute", 0)
        e.advance(3 * HOUR_MS)
        remaining = base.garrison.get("brute", 0)
        assert remaining < initial_brutes, "no desertion occurred"

    def test_desertion_restores_net_zero_or_positive(self) -> None:
        """After desertion the food net rate is ≥ 0."""
        e, bid = self._starvation_base(brutes=50)
        e.advance(5 * HOUR_MS)
        net = e.rates(e.w.bases[bid])["food"]
        assert net >= 0, f"still starving: net={net}"

    def test_desertion_picks_highest_upkeep_first(self) -> None:
        """The stack with the highest total upkeep deserts first."""
        params = _BASE_PARAMS.with_changes(protection_hours=0)
        e = _engine(params)
        bid = _setup_player(e, 1, (5, 0), (7, 0))
        base = e.w.bases[bid]
        base.buildings = {"barracks": 10, "hall": 5}
        base.stock["food"] = 0
        base.residual["food"] = 0
        # 1 ram (stack upkeep = 3000m) + 5 brutes (stack = 5000m) = 8000m total
        # farm L0 produces 20000m; deficit = 0. Use 30 brutes + 1 ram:
        # brute stack = 30000m, ram stack = 3000m; total = 33000 > 20000 → deficit
        # brute stack (30000) > ram stack (3000) → brutes desert first
        base.garrison = {"ram": 1, "brute": 30}
        base.away = {}
        _force_rate_update(e, 1)
        e.advance(3 * HOUR_MS)
        remaining_brutes = base.garrison.get("brute", 0)
        remaining_rams = base.garrison.get("ram", 0)
        net = e.rates(base)["food"]
        assert net >= 0, f"still starving: net={net}"
        # brutes (largest total upkeep stack = 30000) should have deserted; ram intact
        assert remaining_rams == 1, (
            f"ram should be last to desert; got remaining_rams={remaining_rams}"
        )
        assert remaining_brutes < 30, "brutes should have deserted"

    def test_desertion_picks_across_home_and_marching(self) -> None:
        """Desertion removes units from a march when nothing is left at home."""
        params = _BASE_PARAMS.with_changes(protection_hours=0)
        e = _engine(params)
        bid = _setup_player(e, 1, (5, 0), (7, 0))
        bid2 = _setup_player(e, 2, (-5, 0), (-7, 0))
        _clear_protection(e)
        base = e.w.bases[bid]
        base.buildings = {}  # no farm → L0 food production = 20 000m/h
        base.stock["food"] = 0
        base.residual["food"] = 0
        base.garrison = {}
        base.away = {}
        e.w.bases[bid2].garrison = {}
        _give_stock(base, ore=100_000, wood=100_000)

        # Put all units into the march; none at home.
        # 25 brutes: upkeep 25 000m > farm L0 20 000m → deficit 5 000m
        base.garrison["brute"] = 25
        r = e.launch(1, bid, "raid", {"brute": 25}, target_base=bid2)
        assert r.ok, r.code
        march_id = r.data["march_id"]
        march = e.w.marches[march_id]

        brutes_before = march.units.get("brute", 0)
        _force_rate_update(e, 1)
        e.advance(3 * HOUR_MS)

        # home garrison is empty so desertion must come from the march
        brutes_after = march.units.get("brute", 0) if march_id in e.w.marches else 0
        assert brutes_after < brutes_before, "marching brutes were not deserted"

    def test_march_with_no_units_vanishes(self) -> None:
        """A march reduced to zero units is removed from world.marches."""
        params = _BASE_PARAMS.with_changes(protection_hours=0)
        e = _engine(params)
        bid = _setup_player(e, 1, (5, 0), (7, 0))
        bid2 = _setup_player(e, 2, (-5, 0), (-7, 0))
        _clear_protection(e)
        base = e.w.bases[bid]
        base.buildings = {}  # farm L0 = 20 000m
        base.stock["food"] = 0
        base.residual["food"] = 0
        base.garrison = {}
        e.w.bases[bid2].garrison = {}
        _give_stock(base, ore=100_000, wood=100_000)

        # Only 25 brutes total marching; deficit = 5000m; all will eventually desert
        base.garrison["brute"] = 25
        r = e.launch(1, bid, "raid", {"brute": 25}, target_base=bid2)
        assert r.ok, r.code
        march_id = r.data["march_id"]
        _force_rate_update(e, 1)
        e.advance(10 * HOUR_MS)
        assert march_id not in e.w.marches, "deserted march should be removed"

    def test_cargo_trimmed_to_survivors_capacity(self) -> None:
        """When march units desert, cargo is trimmed to remaining capacity."""
        params = _BASE_PARAMS.with_changes(protection_hours=0)
        e = _engine(params)
        bid = _setup_player(e, 1, (5, 0), (7, 0))
        bid2 = _setup_player(e, 2, (-5, 0), (-7, 0))
        _clear_protection(e)
        base = e.w.bases[bid]
        base.buildings = {}  # farm L0 = 20 000m
        base.stock["food"] = 0
        base.residual["food"] = 0
        base.garrison = {}
        e.w.bases[bid2].garrison = {}
        _give_stock(base, ore=100_000, wood=100_000)

        # Send 25 brutes (cargo 40 each) on a long raid; deficit = 5000m
        base.garrison["brute"] = 25
        r = e.launch(1, bid, "raid", {"brute": 25}, target_base=bid2)
        assert r.ok, r.code
        march = e.w.marches[r.data["march_id"]]

        # Load cargo beyond what 20 brutes can hold (20*40 000=800 000m)
        march.cargo = {"ore": 900 * MILLI}  # 900 000m > 800 000m cap for 20 brutes

        _force_rate_update(e, 1)
        e.advance(4 * HOUR_MS)

        if march.id in e.w.marches and march.units:
            survivors = march.units.get("brute", 0)
            cap = e.r.units["brute"].cargo * survivors * MILLI
            total_cargo = sum(march.cargo.values())
            assert total_cargo <= cap, (
                f"cargo {total_cargo} > capacity {cap} for {survivors} brutes"
            )


# ---------------------------------------------------------------------------
# 4. Loot bucket P2 (§6.9)
# ---------------------------------------------------------------------------


class TestLootBucket:
    """12-h loss ≤ 8h production, vault protects, food unlootable."""

    _P2_PARAMS = _BASE_PARAMS.with_changes(
        protection_hours=0,
        bucket_hours=8,
        bucket_refill_hours=12,
    )

    def _raid_pair(self) -> tuple[Engine, int, int, int, int]:
        """(engine, attacker_pid, attacker_bid, defender_pid, defender_bid)."""
        params = self._P2_PARAMS
        e = _engine(params)
        abid = _setup_player(e, 1, (5, 0), (7, 0))
        dbid = _setup_player(e, 2, (5, 2), (7, 2))
        e.w.players[2].protection_until = 0
        e.w.bases[dbid].garrison = {}
        e.w.bases[abid].garrison["brute"] = 10_000
        return e, 1, abid, 2, dbid

    def test_loot_capped_within_first_12h(self) -> None:
        """First raid drains the bucket (≤ 8h hourly_value)."""
        e, _, abid, _, dbid = self._raid_pair()
        dbase = e.w.bases[dbid]
        defender = e.w.players[2]
        _set_stock(dbase, ore=100_000, wood=100_000, gem=100_000)

        r = e.launch(1, abid, "raid", {"brute": 10_000}, target_base=dbid)
        assert r.ok
        e.advance(r.data["arrive_ms"])

        total_looted = sum(x.value_m for x in e.w.loot_log if x.defender == 2)
        hourly = e.hourly_value(defender)
        if hourly > 0:
            cap = self._P2_PARAMS.bucket_hours * hourly
            assert total_looted <= cap, (
                f"looted {total_looted} > bucket cap {cap}"
            )

    def test_bucket_limits_subsequent_raids(self) -> None:
        """After bucket is drained, a second immediate raid yields little loot."""
        e, _, abid, _, dbid = self._raid_pair()
        dbase = e.w.bases[dbid]
        abase = e.w.bases[abid]
        _set_stock(dbase, ore=1_000_000, wood=1_000_000, gem=1_000_000)

        # First raid – drains bucket
        abase.garrison["brute"] = 10_000
        r1 = e.launch(1, abid, "raid", {"brute": 10_000}, target_base=dbid)
        assert r1.ok
        e.advance(r1.data["arrive_ms"])
        _set_stock(dbase, ore=1_000_000, wood=1_000_000, gem=1_000_000)

        # Second raid at same time – bucket near zero, tiny loot
        abase.garrison["brute"] = 10_000
        r2 = e.launch(1, abid, "raid", {"brute": 10_000}, target_base=dbid)
        if r2.ok:
            before_loot = sum(x.value_m for x in e.w.loot_log if x.defender == 2)
            e.advance(r2.data["arrive_ms"])
            after_loot = sum(x.value_m for x in e.w.loot_log if x.defender == 2)
            second_loot = after_loot - before_loot
            hourly = e.hourly_value(e.w.players[2])
            # second loot must be tiny fraction of 8h production
            assert second_loot < hourly, (
                f"bucket should be near 0 but second raid took {second_loot}"
            )

    def test_vault_protects_resources_at_vault_level(self) -> None:
        """Resources at or below vault are never looted."""
        e, _, abid, _, dbid = self._raid_pair()
        rules = e.w.rules
        dbase = e.w.bases[dbid]
        vault = rules.vault_m[0]  # store L0
        # set ore exactly at vault level
        dbase.stock = {
            "ore": vault,
            "wood": vault,
            "gem": vault,
            "food": 200 * MILLI,
        }
        abase = e.w.bases[abid]
        abase.garrison["brute"] = 10_000
        r = e.launch(1, abid, "raid", {"brute": 10_000}, target_base=dbid)
        assert r.ok
        e.advance(r.data["arrive_ms"])
        # nothing above vault → nothing taken
        for res in ("ore", "wood", "gem"):
            assert dbase.stock[res] >= vault, (
                f"{res} dropped below vault: {dbase.stock[res]} < {vault}"
            )

    def test_food_never_looted(self) -> None:
        """Food must never appear in returning march cargo."""
        e, _, abid, _, dbid = self._raid_pair()
        dbase = e.w.bases[dbid]
        _set_stock(dbase, ore=100_000, wood=100_000, gem=100_000, food=100_000)
        abase = e.w.bases[abid]
        abase.garrison["brute"] = 5_000
        e.w.keep_marches = True
        r = e.launch(1, abid, "raid", {"brute": 5_000}, target_base=dbid)
        assert r.ok
        march_id = r.data["march_id"]
        e.advance(r.data["arrive_ms"] + 1)
        # check any match in finished marches
        finished = [m for m in e.w.finished_marches if m.id == march_id]
        m = e.w.marches.get(march_id)
        cargo = finished[0].cargo if finished else (m.cargo if m else {})
        assert "food" not in cargo, f"food found in cargo: {cargo}"


# ---------------------------------------------------------------------------
# 5. Protection / morale / affiliation
# ---------------------------------------------------------------------------


class TestProtectionMoraleAffiliation:
    def _two_players(
        self, extra_params: dict | None = None
    ) -> tuple[Engine, int, int, int, int]:
        p = _BASE_PARAMS.with_changes(**(extra_params or {}))
        e = _engine(p)
        abid = _setup_player(e, 1, (5, 0), (7, 0))
        dbid = _setup_player(e, 2, (5, 2), (7, 2))
        e.w.bases[abid].garrison["brute"] = 200
        return e, 1, abid, 2, dbid

    def test_protected_target_rejected(self) -> None:
        e, _, abid, _, dbid = self._two_players()
        assert e.w.players[2].protection_until > 0
        r = e.launch(1, abid, "raid", {"brute": 10}, target_base=dbid)
        assert not r.ok
        assert r.code == "protected_target"

    def test_attacker_loses_protection_on_hostile_launch(self) -> None:
        e, _, abid, _, dbid = self._two_players({"protection_hours": 72})
        e.w.players[2].protection_until = 0
        attacker = e.w.players[1]
        assert attacker.protection_until > e.w.now_ms
        r = e.launch(1, abid, "raid", {"brute": 10}, target_base=dbid)
        assert r.ok
        assert attacker.protection_until <= e.w.now_ms

    def test_affiliated_players_cannot_attack(self) -> None:
        e, _, abid, _, dbid = self._two_players({"protection_hours": 0})
        _clear_protection(e)  # _dur(0)=1 → need explicit zero
        ra = e.create_alliance(1, "Blades", "BL")
        assert ra.ok
        alliance_id = ra.data["alliance_id"]
        e.invite(1, 2)
        e.accept_invite(2, alliance_id)
        r = e.launch(1, abid, "raid", {"brute": 10}, target_base=dbid)
        assert not r.ok
        assert r.code == "affiliated_target"

    def test_affiliation_ban_persists_after_leaving(self) -> None:
        e, _, abid, _, dbid = self._two_players({"protection_hours": 0})
        _clear_protection(e)
        ra = e.create_alliance(1, "Blades", "BL")
        alliance_id = ra.data["alliance_id"]
        e.invite(1, 2)
        e.accept_invite(2, alliance_id)
        e.leave_alliance(2)
        r = e.launch(1, abid, "raid", {"brute": 10}, target_base=dbid)
        assert not r.ok
        assert r.code == "affiliated_target"

    def test_march_launched_before_alliance_resolves(self) -> None:
        """March sent before players become allies must still resolve normally."""
        e, _, abid, _, dbid = self._two_players({"protection_hours": 0})
        _clear_protection(e)
        e.w.bases[dbid].garrison = {}
        # launch BEFORE forming alliance
        r = e.launch(1, abid, "raid", {"brute": 50}, target_base=dbid)
        assert r.ok
        march_id = r.data["march_id"]
        # now become allies
        ra = e.create_alliance(1, "Blades", "BL")
        e.invite(1, 2)
        e.accept_invite(2, ra.data["alliance_id"])
        # advance to arrival – march must resolve (won or lost)
        e.advance(r.data["arrive_ms"])
        m = e.w.marches.get(march_id)
        if m is not None:
            assert m.status in ("returning", "done")


# ---------------------------------------------------------------------------
# 6. Vacation state machine (§6.11)
# ---------------------------------------------------------------------------


class TestVacationStateMachine:
    _VAC_PARAMS = _BASE_PARAMS.with_changes(
        protection_hours=0,
        vacation_delay_hours=12,
        vacation_min_hours=48,
        vacation_quota_days=14,
        vacation_cooldown_hours=24,
    )

    def _vac_engine(self) -> tuple[Engine, int, int]:
        e = _engine(self._VAC_PARAMS)
        bid = _setup_player(e, 1, (5, 0), (7, 0))
        e.w.players[1].last_hostile_launch_ms = -(10**15)
        return e, 1, bid

    def test_pending_forbids_hostile_launch(self) -> None:
        e, pid, bid = self._vac_engine()
        bid2 = _setup_player(e, 2, (-5, 0), (-7, 0))
        e.w.bases[bid].garrison["brute"] = 100
        rv = e.request_vacation(pid)
        assert rv.ok
        r = e.launch(pid, bid, "raid", {"brute": 10}, target_base=bid2)
        assert not r.ok
        assert r.code == "vacation_pending"

    def test_marches_before_request_still_resolve(self) -> None:
        """March sent before vacation request must arrive and resolve."""
        e, pid, bid = self._vac_engine()
        bid2 = _setup_player(e, 2, (-5, 0), (-7, 0))
        _clear_protection(e, 2)  # player 2 has protection_until=1 even with hours=0
        e.w.bases[bid2].garrison = {}
        e.w.bases[bid].garrison["brute"] = 200
        # launch BEFORE vacation request
        rl = e.launch(pid, bid, "raid", {"brute": 50}, target_base=bid2)
        assert rl.ok, rl.code
        march_id = rl.data["march_id"]
        # Reset hostile flag so vacation can be requested immediately
        e.w.players[pid].last_hostile_launch_ms = -(10**15)
        rv = e.request_vacation(pid)
        assert rv.ok
        e.advance(rl.data["arrive_ms"])
        # march must have resolved, not been cancelled by vacation
        m = e.w.marches.get(march_id)
        assert m is None or m.status in ("returning", "done")

    def test_active_vacation_stops_production(self) -> None:
        """During active vacation all production rates are zero."""
        e, pid, bid = self._vac_engine()
        rv = e.request_vacation(pid)
        assert rv.ok
        player = e.w.players[pid]
        e.advance(player.vacation_at)
        assert player.vacation_state == "active"
        r = e.rates(e.w.bases[bid])
        assert all(v == 0 for v in r.values()), f"non-zero rates on vacation: {r}"

    def test_attack_at_pending_target_rejected(self) -> None:
        """Attacking a player whose vacation is pending → target_on_vacation."""
        params = _BASE_PARAMS.with_changes(
            protection_hours=0,
            vacation_delay_hours=1,
            vacation_min_hours=1,
            vacation_quota_days=14,
            vacation_cooldown_hours=1,
        )
        e = _engine(params)
        abid = _setup_player(e, 1, (5, 0), (7, 0))
        dbid = _setup_player(e, 2, (-5, 0), (-7, 0))
        e.w.players[2].last_hostile_launch_ms = -(10**15)
        e.advance(params.vacation_delay_hours * HOUR_MS)
        rv = e.request_vacation(2)
        assert rv.ok
        e.w.bases[abid].garrison["brute"] = 100
        r = e.launch(1, abid, "raid", {"brute": 10}, target_base=dbid)
        assert not r.ok
        assert r.code == "target_on_vacation"

    def test_attack_at_active_vacation_target_rejected(self) -> None:
        """Attacking a player on active vacation → target_on_vacation."""
        params = _BASE_PARAMS.with_changes(
            protection_hours=0,
            vacation_delay_hours=1,
            vacation_min_hours=1,
            vacation_quota_days=14,
            vacation_cooldown_hours=1,
        )
        e = _engine(params)
        abid = _setup_player(e, 1, (5, 0), (7, 0))
        dbid = _setup_player(e, 2, (-5, 0), (-7, 0))
        e.w.players[2].last_hostile_launch_ms = -(10**15)
        e.advance(params.vacation_delay_hours * HOUR_MS)
        e.request_vacation(2)
        player2 = e.w.players[2]
        e.advance(player2.vacation_at)
        assert player2.vacation_state == "active"
        e.w.bases[abid].garrison["brute"] = 100
        r = e.launch(1, abid, "raid", {"brute": 10}, target_base=dbid)
        assert not r.ok
        assert r.code == "target_on_vacation"

    def test_min_stay_enforced(self) -> None:
        e, pid, _ = self._vac_engine()
        rv = e.request_vacation(pid)
        assert rv.ok
        player = e.w.players[pid]
        e.advance(player.vacation_at)
        r = e.exit_vacation(pid)
        assert not r.ok
        assert r.code == "vacation_minimum"

    def test_quota_exhausted_prevents_new_vacation(self) -> None:
        """Player who has used all quota cannot request another."""
        params = _BASE_PARAMS.with_changes(
            protection_hours=0,
            vacation_delay_hours=1,
            vacation_min_hours=1,
            vacation_quota_days=1,
            vacation_cooldown_hours=1,
        )
        e = _engine(params)
        _setup_player(e, 1, (5, 0), (7, 0))
        e.w.players[1].last_hostile_launch_ms = -(10**15)
        e.advance(params.vacation_delay_hours * HOUR_MS)
        e.request_vacation(1)
        player = e.w.players[1]
        e.advance(player.vacation_at + params.vacation_quota_days * DAY_MS + 1)
        # vacation auto-ended; used up quota
        assert player.vacation_state == "none"
        assert player.vacation_used_ms >= params.vacation_quota_days * DAY_MS
        e.advance(player.vacation_cooldown_until + 1)
        r = e.request_vacation(1)
        assert not r.ok
        assert r.code == "vacation_quota"

    def test_cooldown_prevents_immediate_re_request(self) -> None:
        e, pid, _ = self._vac_engine()
        e.request_vacation(pid)
        e.cancel_vacation(pid)
        r = e.request_vacation(pid)
        assert not r.ok
        assert r.code == "vacation_cooldown"


# ---------------------------------------------------------------------------
# 7. Settle
# ---------------------------------------------------------------------------


class TestSettle:
    """Slot reservation, double-settle rejection, tile-taken bounce."""

    def _settle_engine(self) -> tuple[Engine, int, int]:
        params = _BASE_PARAMS.with_changes(protection_hours=0)
        e = _engine(params)
        bid = _setup_player(e, 1, (5, 0), (7, 0))
        base = e.w.bases[bid]
        base.garrison["settler"] = 2
        base.buildings["barracks"] = 10
        base.buildings["hall"] = 5
        _give_stock(base, ore=100_000, wood=100_000, gem=100_000)
        # charter L1 → 2 base slots
        e.w.players[1].research["charter"] = 1
        return e, 1, bid

    def test_second_settler_rejected_when_slot_full(self) -> None:
        """With 1 base + 1 reserved slot → no_base_slot for second settler."""
        e, pid, bid = self._settle_engine()
        player = e.w.players[pid]
        # 1 base, charter=1 → 2 slots; 1 settle reserves 1 slot
        r1 = e.launch(pid, bid, "settle", {"settler": 1}, target_xy=(10, 0))
        assert r1.ok, r1.code
        assert player.reserved_slots == 1
        r2 = e.launch(pid, bid, "settle", {"settler": 1}, target_xy=(12, 0))
        assert not r2.ok
        assert r2.code == "no_base_slot"

    def test_tile_taken_causes_bounce(self) -> None:
        """Occupying the target tile before settler arrives → bounced."""
        e, pid, bid = self._settle_engine()
        e.w.keep_marches = True
        target_xy = (10, 0)
        r = e.launch(pid, bid, "settle", {"settler": 1}, target_xy=target_xy)
        assert r.ok, r.code
        march_id = r.data["march_id"]
        # place a camp at the target tile before arrival
        e.add_camp(*target_xy)
        e.advance(r.data["arrive_ms"])
        # check outcome
        finished = [m for m in e.w.finished_marches if m.id == march_id]
        m = e.w.marches.get(march_id)
        outcome = finished[0].outcome if finished else (m.status if m else "unknown")
        assert outcome in ("bounced", "returning"), f"expected bounce, got: {outcome}"

    def test_successful_settle_creates_new_base(self) -> None:
        """Settler arriving at free tile creates a new player base."""
        e, pid, bid = self._settle_engine()
        base_count_before = len(e.w.players[pid].base_ids)
        r = e.launch(pid, bid, "settle", {"settler": 1}, target_xy=(15, 0))
        assert r.ok, r.code
        e.advance(r.data["arrive_ms"])
        assert len(e.w.players[pid].base_ids) == base_count_before + 1


# ---------------------------------------------------------------------------
# 8. Monument (§6.15)
# ---------------------------------------------------------------------------


class TestMonument:
    """Sites spawn day 18, qualify gate, capture, contributions, hold."""

    # Tiny params: 2 levels, cheap, fast build, short hold
    _M = _BASE_PARAMS.with_changes(
        protection_hours=0,
        monument_levels=2,
        monument_base=10,
        monument_growth_x100=100,
        monument_build_hours=1,
        monument_hold_hours=1,
        site_qualify_members=3,
        site_day=18,
        round_days=28,
    )

    def _qualified_world(self) -> tuple[Engine, int, list[int]]:
        """3-player alliance in a small world; returns (engine, alliance_id, bids)."""
        e = _engine(self._M, radius=10)
        bids = []
        for i, (xy, txy) in enumerate(
            [((1, 0), (3, 0)), ((1, 2), (3, 2)), ((1, 4), (3, 4))], start=1
        ):
            bid = _setup_player(e, i, xy, txy)
            bids.append(bid)
            e.w.players[i].protection_until = 0
            _give_stock(e.w.bases[bid], ore=10_000_000, wood=10_000_000, gem=10_000_000)
            e.w.bases[bid].garrison["brute"] = 5_000
        ra = e.create_alliance(1, "AlphaTeam", "AT")
        assert ra.ok
        alliance_id = ra.data["alliance_id"]
        for pid in [2, 3]:
            e.invite(1, pid)
            e.accept_invite(pid, alliance_id)
        return e, alliance_id, bids

    def test_sites_spawn_on_day_18_for_qualified_alliance(self) -> None:
        e, _, _ = self._qualified_world()
        assert len(e.w.sites) == 0
        e.advance(18 * DAY_MS + 1)
        assert len(e.w.sites) >= 1, "sites should have spawned"

    def test_no_sites_when_not_enough_members(self) -> None:
        """Only 2 active members → no sites spawn."""
        m = self._M.with_changes(site_qualify_members=3)
        e = _engine(m, radius=10)
        for i, (xy, txy) in enumerate(
            [((1, 0), (3, 0)), ((1, 2), (3, 2))], start=1
        ):
            _setup_player(e, i, xy, txy)
        ra = e.create_alliance(1, "SmallTeam", "SM")
        e.invite(1, 2)
        e.accept_invite(2, ra.data["alliance_id"])
        e.advance(18 * DAY_MS + 1)
        assert len(e.w.sites) == 0

    def test_capture_npc_site_assigns_alliance(self) -> None:
        """Winning an attack on an NPC site gives it to the attacker's alliance."""
        e, alliance_id, bids = self._qualified_world()
        e.advance(18 * DAY_MS + 1)
        assert e.w.sites, "sites must spawn"
        site_base_id = next(iter(e.w.sites))
        site_base = e.w.bases[site_base_id]
        site_base.garrison = {}  # easy win
        r = e.launch(1, bids[0], "attack", {"brute": 5_000}, target_base=site_base_id)
        assert r.ok, r.code
        e.advance(r.data["arrive_ms"])
        assert e.w.sites[site_base_id].alliance_id == alliance_id

    def test_contributions_trigger_build(self) -> None:
        """Delivering a full recipe makes the site start building."""
        e, _alliance_id, bids = self._qualified_world()
        e.advance(18 * DAY_MS + 1)
        assert e.w.sites
        site_base_id = next(iter(e.w.sites))
        site_base = e.w.bases[site_base_id]
        site_base.garrison = {}
        r = e.launch(1, bids[0], "attack", {"brute": 5_000}, target_base=site_base_id)
        assert r.ok, r.code
        e.advance(r.data["arrive_ms"])
        site = e.w.sites[site_base_id]
        assert site.alliance_id is not None

        rules = e.w.rules
        recipe = rules.monument_recipe_m[1]
        abase = e.w.bases[bids[0]]
        for res, amt in recipe.items():
            abase.stock[res] = amt * 5
        abase.garrison["brute"] = max(abase.garrison.get("brute", 0), 100)
        rc = e.launch(
            1, bids[0], "contribute",
            {"brute": 1},
            target_base=site_base_id,
            cargo=dict(recipe),
        )
        assert rc.ok, rc.code
        e.advance(rc.data["arrive_ms"])
        assert site.state == "building"
        assert site.build_end_ms > e.w.now_ms

    def _fund_and_build(self, e: Engine, pid: int, bid: int, site_id: int) -> None:
        site = e.w.sites[site_id]
        recipe = e.w.rules.monument_recipe_m[site.level + 1]
        abase = e.w.bases[bid]
        for res, amt in recipe.items():
            abase.stock[res] = amt * 10
        abase.garrison["brute"] = max(abase.garrison.get("brute", 0), 100)
        rc = e.launch(
            pid, bid, "contribute", {"brute": 1},
            target_base=site_id, cargo=dict(recipe),
        )
        assert rc.ok, rc.code
        e.advance(rc.data["arrive_ms"])
        assert site.state == "building"
        e.advance(site.build_end_ms)

    def _capture(self, e: Engine, pid: int, bid: int, site_id: int) -> None:
        e.w.bases[site_id].garrison = {}
        for m in list(e.w.marches.values()):
            if m.status == "stationed" and m.target_base == site_id:
                m.units = {}
        e.w.bases[bid].garrison["brute"] = 5_000
        r = e.launch(pid, bid, "attack", {"brute": 5_000}, target_base=site_id)
        assert r.ok, r.code
        e.advance(r.data["arrive_ms"])

    def test_hold_at_max_level_wins(self) -> None:
        """Alliance holding max level for monument_hold_hours wins."""
        e, alliance_id, bids = self._qualified_world()
        e.advance(18 * DAY_MS + 1)
        site_id = next(iter(e.w.sites))
        self._capture(e, 1, bids[0], site_id)
        for _ in range(e.p.monument_levels):
            self._fund_and_build(e, 1, bids[0], site_id)
        site = e.w.sites[site_id]
        assert site.level == e.p.monument_levels
        assert e.w.winner_alliance is None
        e.advance(site.hold_until)
        assert e.w.winner_alliance == alliance_id
        assert e.w.ended

    def _four_alliances(self) -> tuple[Engine, list[int], list[int]]:
        """Four alliances of 3 → two sites. Returns (engine, aids, bids)."""
        e = _engine(self._M, radius=14)
        bids, aids = [], []
        spots = [(x, y) for y in (-9, -5, 5, 9) for x in (-6, -1, 4)]
        for pid, (x, y) in enumerate(spots, start=1):
            bid = _setup_player(e, pid, (x, y), (x + 1, y + 2))
            bids.append(bid)
            e.w.players[pid].protection_until = 0
        for g in range(4):
            leader = 1 + 3 * g
            aid = e.create_alliance(leader, f"A{g}", f"A{g}").data["alliance_id"]
            aids.append(aid)
            for pid in (leader + 1, leader + 2):
                e.invite(leader, pid)
                assert e.accept_invite(pid, aid).ok
        e.advance(18 * DAY_MS + 1)
        assert len(e.w.sites) == 2
        return e, aids, bids

    def test_enemy_capture_drops_a_level_and_changes_owner(self) -> None:
        e, aids, bids = self._four_alliances()
        site_id = sorted(e.w.sites)[0]
        self._capture(e, 1, bids[0], site_id)
        self._fund_and_build(e, 1, bids[0], site_id)
        self._fund_and_build(e, 1, bids[0], site_id)
        site = e.w.sites[site_id]
        assert site.level == 2
        self._capture(e, 4, bids[3], site_id)  # alliance 2 holds no site
        assert site.alliance_id == aids[1]
        assert site.level == 1
        assert site.contributed == {"ore": 0, "wood": 0, "gem": 0}

    def test_alliance_holding_a_site_only_sieges(self) -> None:
        e, aids, bids = self._four_alliances()
        first, second = sorted(e.w.sites)
        self._capture(e, 1, bids[0], first)
        self._fund_and_build(e, 1, bids[0], first)
        self._capture(e, 4, bids[3], second)  # alliance 2 now holds a site
        assert e.w.sites[second].alliance_id == aids[1]
        self._capture(e, 4, bids[3], first)  # no rams: siege does nothing
        site = e.w.sites[first]
        assert site.alliance_id == aids[0]
        assert site.level == 1

    def test_alliance_with_site_cannot_attack_npc_site(self) -> None:
        e, _aids, bids = self._four_alliances()
        first, second = sorted(e.w.sites)
        self._capture(e, 1, bids[0], first)
        e.w.bases[bids[0]].garrison["brute"] = 10
        r = e.launch(1, bids[0], "attack", {"brute": 10}, target_base=second)
        assert r.code == "already_holds_site"


# ---------------------------------------------------------------------------
# 9. Round-end barrier
# ---------------------------------------------------------------------------


class TestRoundEnd:
    """Past end_ms: ended=True; actions rejected; further advance is noop."""

    def test_advance_past_end_sets_ended(self) -> None:
        e = _engine()
        _setup_player(e)
        assert not e.w.ended
        e.advance(28 * DAY_MS + HOUR_MS)
        assert e.w.ended

    def test_actions_rejected_after_end(self) -> None:
        e = _engine()
        bid = _setup_player(e)
        _give_stock(e.w.bases[bid], ore=1_000_000, wood=1_000_000)
        e.advance(28 * DAY_MS + HOUR_MS)
        assert e.w.ended
        r = e.build(1, bid, "quarry")
        assert not r.ok
        # Should be round_ended (player is kept active via _BASE_PARAMS long inactive window)
        assert r.code == "round_ended"

    def test_advance_after_ended_is_noop(self) -> None:
        e = _engine()
        _setup_player(e)
        e.advance(28 * DAY_MS + HOUR_MS)
        now_before = e.w.now_ms
        e.advance(30 * DAY_MS)
        assert e.w.now_ms == now_before


# ---------------------------------------------------------------------------
# 10. Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    """Two worlds running identical action scripts → identical state digest."""

    def _digest(self, w: World) -> str:
        def _sanitize(obj: object) -> object:
            """Recursively replace un-serialisable types."""
            if isinstance(obj, dict):
                return {
                    (str(k) if isinstance(k, tuple) else k): _sanitize(v)
                    for k, v in obj.items()
                }
            if isinstance(obj, list):
                return [_sanitize(v) for v in obj]
            if isinstance(obj, (set, frozenset)):
                return sorted(_sanitize(v) for v in obj)
            if isinstance(obj, tuple):
                return [_sanitize(v) for v in obj]
            return obj

        raw = dataclasses.asdict(w)  # type: ignore[arg-type]
        return hashlib.sha256(
            json.dumps(_sanitize(raw), sort_keys=True).encode()
        ).hexdigest()

    def _run_script(self) -> World:
        params = _BASE_PARAMS.with_changes(protection_hours=0)
        e = _engine(params)
        e.w.keep_marches = True
        e.w.keep_reports = True

        bid1 = _setup_player(e, 1, (5, 0), (7, 0))
        bid2 = _setup_player(e, 2, (-5, 0), (-7, 0))
        _clear_protection(e)
        b1 = e.w.bases[bid1]
        b2 = e.w.bases[bid2]
        _give_stock(b1, ore=500_000, wood=500_000, gem=100_000)
        b2.garrison = {}
        b1.garrison["brute"] = 200
        # Give barracks L1 so we can train tier-1 units
        b1.buildings["barracks"] = 1
        b1.buildings["hall"] = 1

        r = e.build(1, bid1, "quarry")
        assert r.ok
        e.advance(2 * HOUR_MS)

        b1.garrison["brute"] = 100
        r2 = e.train(1, bid1, "brute", 10)
        assert r2.ok, r2.code
        e.advance(4 * HOUR_MS)

        r3 = e.launch(1, bid1, "raid", {"brute": 50}, target_base=bid2)
        if r3.ok:
            e.advance(r3.data["arrive_ms"])

        e.advance(DAY_MS)
        return e.w

    def test_two_runs_identical(self) -> None:
        w1 = self._run_script()
        w2 = self._run_script()
        assert self._digest(w1) == self._digest(w2), "engine is non-deterministic"


# ---------------------------------------------------------------------------
# Late-joiner head start (§6.17)
# ---------------------------------------------------------------------------


class TestHeadStart:
    """Late joiners start at a percentile of existing players' levels."""

    def _world_with_veterans(self, pct: int) -> Engine:
        e = _engine(_BASE_PARAMS.with_changes(headstart_pct=pct))
        levels = [(2, 1), (6, 3), (10, 5), (14, 7)]  # (quarry, hall)
        for pid, (quarry, hall) in enumerate(levels, start=1):
            bid = _setup_player(e, pid, (pid * 4, 0), (pid * 4, 2))
            e.w.bases[bid].buildings.update(quarry=quarry, hall=hall)
        e.advance(8 * DAY_MS)
        for pid in range(1, 5):
            e.touch(pid)
        return e

    def test_late_joiner_starts_at_the_percentile(self) -> None:
        e = self._world_with_veterans(pct=50)
        bid = _setup_player(e, 9, (0, 20), (2, 20))
        built = e.w.bases[bid].buildings
        assert built["quarry"] == 6 and built["hall"] == 3
        assert e.w.players[9].power > 0  # seeded levels count toward power

    def test_levels_never_exceed_the_seeded_hall_cap(self) -> None:
        e = self._world_with_veterans(pct=100)
        bid = _setup_player(e, 9, (0, 20), (2, 20))
        built = e.w.bases[bid].buildings
        cap = e.w.rules.hall_cap(built["hall"])
        assert all(lv <= cap for b, lv in built.items() if b != "hall")

    def test_disabled_and_day_one_joiners_get_nothing(self) -> None:
        e = self._world_with_veterans(pct=0)
        bid = _setup_player(e, 9, (0, 20), (2, 20))
        assert e.w.bases[bid].buildings == {"quarry": 1, "sawmill": 1, "farm": 1}
        fresh = _engine(_BASE_PARAMS.with_changes(headstart_pct=50))
        bid = _setup_player(fresh, 1, (4, 0), (4, 2))
        assert fresh.w.bases[bid].buildings == {"quarry": 1, "sawmill": 1, "farm": 1}
