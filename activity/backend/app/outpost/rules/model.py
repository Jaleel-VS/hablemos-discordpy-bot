"""Rule definitions, tunable parameters and the integer-table generator.

Static unit/building/tech definitions follow plans/outpost.md §6. Every
number a balance sweep may vary lives on ``Params``. ``build_ruleset`` turns
definitions + params into integer level tables once; the engine never
evaluates ``exp``/``pow`` at runtime (§7.6).
"""
import hashlib
import json
import math
from dataclasses import asdict, dataclass, field, replace
from functools import lru_cache

HOUR_MS = 3_600_000
DAY_MS = 24 * HOUR_MS
MILLI = 1000

RESOURCES = ("ore", "wood", "gem", "food")
BUILD_RES = ("ore", "wood", "gem")
# Trade value of one unit of each resource, in milli-value (§6.1).
VALUE_PER_UNIT = {"ore": 1000, "wood": 1000, "gem": 2500, "food": 0}


def value_m(amount_m: dict[str, int]) -> int:
    """Trade value (milli-value) of an amount given in milli-units."""
    return sum(
        amount_m.get(r, 0) * VALUE_PER_UNIT[r] // MILLI for r in BUILD_RES
    )


@dataclass(frozen=True, slots=True)
class Params:
    """Every tunable knob. Defaults are ruleset v1 (plans/outpost.md §6)."""

    speed_pct: int = 100
    build_slots: int = 2
    build_divisor: int = 2500
    hall_cap_mult: int = 2
    hall_cap_base: int = 5
    prod_mult_pct: int = 100
    unit_cost_mult_pct: int = 100
    upkeep_mult_pct: int = 100
    store_scale: int = 4000
    vault_pct: int = 10
    loot_pct: int = 50
    bucket_hours: int = 4
    bucket_refill_hours: int = 12
    protection_hours: int = 72
    catchup_max_pct: int = 0  # extra production %; superseded by headstart
    # late joiners start at this percentile of players' building levels
    # (0 = off; §6.17)
    headstart_pct: int = 10
    # 1 = players also see a leaderboard of everyone who joined the same
    # round week (their "cohort"); 0 = only the server-wide board
    cohort_boards: int = 1
    catchup_days: int = 5
    camps_per_player_x10: int = 5
    camp_respawn_hours: int = 6
    camp_stock_base: int = 6000
    camp_warden_base: int = 8
    monument_base: int = 150_000
    monument_growth_x100: int = 135
    monument_levels: int = 10
    monument_build_hours: int = 6
    monument_hold_hours: int = 24
    site_qualify_members: int = 3
    site_day: int = 18
    join_close_day: int = 21
    round_days: int = 28
    march_slots_base: int = 3
    per_target_cap: int = 3
    alliance_cap: int = 8
    affiliation_ban_days: int = 7
    alliance_hop_hours: int = 24
    inactive_hours: int = 72
    gone_days: int = 7
    vacation_delay_hours: int = 12
    vacation_min_hours: int = 48
    vacation_quota_days: int = 14
    vacation_cooldown_hours: int = 24
    settle_min_distance: int = 3

    def to_json(self) -> dict[str, int]:
        """Plain dict for storage."""
        return asdict(self)

    def with_changes(self, **changes: int) -> "Params":
        """Copy with some fields replaced (unknown names raise TypeError)."""
        return replace(self, **changes)


@dataclass(frozen=True, slots=True)
class BuildingSpec:
    """Static building definition before table generation."""

    id: str
    base_cost: dict[str, int]
    growth: float
    max_level: int
    requires: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class UnitSpec:
    """Static unit definition (§6.3)."""

    id: str
    tier: int
    cost: dict[str, int]
    upkeep: int
    atk: int
    cls: str
    def_foot: int
    def_swift: int
    speed: int
    cargo: int
    train_s: int


@dataclass(frozen=True, slots=True)
class TechSpec:
    """Static research definition (§6.4)."""

    id: str
    base_cost: dict[str, int]
    growth: float
    max_level: int


@dataclass(frozen=True, slots=True)
class BuildingDef:
    """Generated building tables; index = target level (index 0 unused)."""

    id: str
    max_level: int
    requires: dict[str, int]
    cost_m: tuple[dict[str, int], ...]
    cost_value_m: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class UnitDef:
    """Unit stats with costs scaled by params, in milli-units."""

    id: str
    tier: int
    cost_m: dict[str, int]
    value_m: int
    upkeep_m: int  # milli-food per hour
    atk: int
    cls: str
    def_foot: int
    def_swift: int
    speed: int
    cargo: int
    train_ms: int


@dataclass(frozen=True, slots=True)
class TechDef:
    """Generated research tables; index = target level."""

    id: str
    max_level: int
    cost_m: tuple[dict[str, int], ...]
    cost_value_m: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class CampTier:
    """NPC camp contents for one ring tier (§6.12)."""

    tier: int
    stock_m: dict[str, int]
    garrison: dict[str, int]


@dataclass(frozen=True, slots=True)
class Ruleset:
    """Everything the engine reads; integers only."""

    params: Params
    buildings: dict[str, BuildingDef]
    units: dict[str, UnitDef]
    techs: dict[str, TechDef]
    # production per hour (milli-units) by resource and producer level
    prod_m: dict[str, tuple[int, ...]]
    producer_of: dict[str, str]
    cap_m: tuple[int, ...]
    vault_m: tuple[int, ...]
    camp_tiers: dict[int, CampTier]
    monument_cost_value_m: tuple[int, ...]
    monument_recipe_m: tuple[dict[str, int], ...]
    barracks_tier_level: dict[int, int]
    version: str

    def hall_cap(self, hall_level: int) -> int:
        """Max level of any non-hall building for a given hall level."""
        p = self.params
        return p.hall_cap_mult * hall_level + p.hall_cap_base


def _level_costs(
    base: dict[str, int], growth: float, max_level: int, mult_pct: int
) -> tuple[tuple[dict[str, int], ...], tuple[int, ...]]:
    costs: list[dict[str, int]] = [{}]
    values: list[int] = [0]
    for level in range(1, max_level + 1):
        c = {
            r: math.ceil(v * growth ** (level - 1) * mult_pct / 100) * MILLI
            for r, v in base.items()
            if v
        }
        costs.append(c)
        values.append(value_m(c))
    return tuple(costs), tuple(values)


def generate(
    params: Params,
    buildings: tuple[BuildingSpec, ...],
    units: tuple[UnitSpec, ...],
    techs: tuple[TechSpec, ...],
    production: dict[str, tuple[str, int, int]],
    barracks_tier_level: dict[int, int],
) -> Ruleset:
    """Generate integer tables from static specs and params."""
    bdefs = {}
    for b in buildings:
        costs, values = _level_costs(b.base_cost, b.growth, b.max_level, 100)
        bdefs[b.id] = BuildingDef(
            b.id, b.max_level, dict(b.requires), costs, values
        )
    udefs = {}
    for u in units:
        cost_m = {
            r: v * MILLI * params.unit_cost_mult_pct // 100
            for r, v in u.cost.items()
            if v
        }
        udefs[u.id] = UnitDef(
            id=u.id,
            tier=u.tier,
            cost_m=cost_m,
            value_m=value_m(cost_m),
            upkeep_m=u.upkeep * MILLI * params.upkeep_mult_pct // 100,
            atk=u.atk,
            cls=u.cls,
            def_foot=u.def_foot,
            def_swift=u.def_swift,
            speed=u.speed,
            cargo=u.cargo,
            train_ms=u.train_s * 1000,
        )
    tdefs = {}
    for t in techs:
        costs, values = _level_costs(t.base_cost, t.growth, t.max_level, 100)
        tdefs[t.id] = TechDef(t.id, t.max_level, costs, values)

    prod_m: dict[str, tuple[int, ...]] = {}
    producer_of: dict[str, str] = {}
    for res, (building, coef, flat) in production.items():
        top = bdefs[building].max_level
        prod_m[res] = tuple(
            int((coef * lv * 1.1**lv + flat) * MILLI)
            * params.prod_mult_pct
            // 100
            for lv in range(top + 1)
        )
        producer_of[res] = building
    store_top = bdefs["store"].max_level
    cap_m = tuple(
        params.store_scale * math.floor(2.5 * math.exp(20 * lv / 33)) * MILLI
        for lv in range(store_top + 1)
    )
    vault_m = tuple(c * params.vault_pct // 100 for c in cap_m)

    camp_tiers = {}
    for tier in range(1, 7):
        stock_value = params.camp_stock_base * 2 ** (tier - 1)
        per_res_value = stock_value // 3
        stock_m = {
            r: per_res_value * MILLI * MILLI // VALUE_PER_UNIT[r]
            for r in BUILD_RES
        }
        garrison = {"warden": params.camp_warden_base * 2 ** (tier - 1)}
        if tier >= 3:
            garrison["bulwark"] = 2 ** (tier - 1)
        camp_tiers[tier] = CampTier(tier, stock_m, garrison)

    mon_values = [0]
    mon_recipes: list[dict[str, int]] = [{}]
    for level in range(1, params.monument_levels + 1):
        v = math.ceil(
            params.monument_base
            * (params.monument_growth_x100 / 100) ** (level - 1)
        )
        mon_values.append(v * MILLI)
        mon_recipes.append(
            {
                "ore": math.ceil(v * 0.4) * MILLI,
                "wood": math.ceil(v * 0.4) * MILLI,
                "gem": math.ceil(v * 0.2 / 2.5) * MILLI,
            }
        )

    tables = {
        "params": params.to_json(),
        "b": {k: [v.cost_value_m, v.max_level] for k, v in bdefs.items()},
        "u": {k: [v.value_m, v.upkeep_m, v.atk] for k, v in udefs.items()},
        "p": prod_m,
        "c": cap_m,
        "m": mon_values,
    }
    version = hashlib.sha256(
        json.dumps(tables, sort_keys=True, default=list).encode()
    ).hexdigest()[:16]
    return Ruleset(
        params=params,
        buildings=bdefs,
        units=udefs,
        techs=tdefs,
        prod_m=prod_m,
        producer_of=producer_of,
        cap_m=cap_m,
        vault_m=vault_m,
        camp_tiers=camp_tiers,
        monument_cost_value_m=tuple(mon_values),
        monument_recipe_m=tuple(mon_recipes),
        barracks_tier_level=dict(barracks_tier_level),
        version=version,
    )


@lru_cache(maxsize=256)
def cached(params: Params) -> Ruleset:
    """Ruleset v1 for these params, generated once per distinct params."""
    from .v1 import build_ruleset  # local import avoids a module cycle

    return build_ruleset(params)
