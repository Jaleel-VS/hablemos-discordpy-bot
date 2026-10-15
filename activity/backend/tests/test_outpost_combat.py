"""Tests for app.outpost.engine.combat and app.outpost.engine.fixed.

All tests are fully deterministic (no randomness).
Run from activity/backend:  ../../.venv/bin/python -m pytest -q tests/test_outpost_combat.py
"""

import pytest
from app.outpost.engine.combat import (
    BattleResult,
    StackKey,
    UnitStats,
    allocate_loot,
    apportion,
    morale_q,
    resolve_battle,
    resolve_scout,
    siege_levels,
)
from app.outpost.engine.fixed import Q, pow15

# ---------------------------------------------------------------------------
# Unit stats used across tests (subset of §6.3)
# ---------------------------------------------------------------------------

BRUTE = UnitStats(atk=40, cls="foot", def_foot=15, def_swift=10, cargo=40, value_m=100)
WARDEN = UnitStats(atk=10, cls="foot", def_foot=40, def_swift=50, cargo=15, value_m=90)
BULWARK = UnitStats(atk=10, cls="foot", def_foot=130, def_swift=110, cargo=0, value_m=300)
OUTRIDER = UnitStats(atk=55, cls="swift", def_foot=20, def_swift=25, cargo=110, value_m=240)
SCOUT_UNIT = UnitStats(atk=0, cls="-", def_foot=2, def_swift=2, cargo=0, value_m=50)
HAULER = UnitStats(atk=0, cls="-", def_foot=5, def_swift=5, cargo=600, value_m=200)

STATS: dict[str, UnitStats] = {
    "brute": BRUTE,
    "warden": WARDEN,
    "bulwark": BULWARK,
    "outrider": OUTRIDER,
    "scout": SCOUT_UNIT,
    "hauler": HAULER,
}

_NO_MORALE = Q  # full morale (no penalty)
_ARMOR: dict[int, int] = {}  # no armor bonus


def _battle(
    att: dict[StackKey, int],
    defs: dict[StackKey, int],
    *,
    arms: int = 0,
    armor: dict[int, int] | None = None,
    wall: int = 0,
    m_q: int = Q,
    raid: bool = False,
) -> BattleResult:
    return resolve_battle(
        att,
        defs,
        STATS,
        arms_level=arms,
        armor_by_owner=armor or {},
        wall=wall,
        morale_q=m_q,
        raid=raid,
    )


# ---------------------------------------------------------------------------
# pow15 / fixed-point
# ---------------------------------------------------------------------------


def test_pow15_unit_ratio():
    # (1)^1.5 = 1 → Q
    assert pow15(Q, Q) == Q


def test_pow15_half():
    # (0.5)^1.5 ≈ 0.3536
    result = pow15(Q // 2, Q)
    assert 353_000_000 <= result <= 354_000_000


def test_pow15_zero_numerator():
    assert pow15(0, Q) == 0


# ---------------------------------------------------------------------------
# Attacker wins
# ---------------------------------------------------------------------------


def test_attacker_wins_attack_mode():
    # 100 brutes (atk 40) vs 20 wardens (def_foot 40)
    att = {(1, "brute"): 100}
    defs = {(2, "warden"): 20}
    r = _battle(att, defs)
    assert r.attacker_won is True
def test_attacker_wins_raid_mode():
    # Use balanced numbers so x is not tiny (avoids loser losing ~all)
    # 200 brutes vs 50 wardens (def_foot=40) pure-foot attack, raid mode
    # A=8000, D_units=50*40=2000 → D=2000; x = pow15(2000,8000) ≈ 0.125Q
    # loser_frac = Q*Q//(Q+x) ≈ 0.889*Q → defender loses ~45/50 (not all 50)
    att = {(1, "brute"): 200}
    defs = {(2, "warden"): 50}
    r = _battle(att, defs, raid=True)
    assert r.attacker_won is True
    assert r.def_losses[(2, "warden")] < 50  # partial losses (not all die)


# ---------------------------------------------------------------------------
# Defender wins
# ---------------------------------------------------------------------------


def test_defender_wins_attack_mode():
    att = {(1, "brute"): 5}
    defs = {(2, "bulwark"): 50}
    r = _battle(att, defs)
    assert r.attacker_won is False
    assert r.att_losses[(1, "brute")] == 5  # loser loses all


def test_defender_wins_raid_mode():
    # 100 brutes vs 50 bulwarks (def_foot=130): defender wins with partial att losses
    # A=4000, D_units=50*130=6500; x=pow15(4000,6500)≈0.483Q
    # loser_frac≈0.674Q → att loses ~68/100 (not all)
    att = {(1, "brute"): 100}
    defs = {(2, "bulwark"): 50}
    r = _battle(att, defs, raid=True)
    assert r.attacker_won is False
    assert r.att_losses[(1, "brute")] < 100  # partial


# ---------------------------------------------------------------------------
# Tie rules (A == D)
# ---------------------------------------------------------------------------


def test_tie_attack_mode_mutual_annihilation():
    # Craft a scenario where A == D exactly.
    # brute atk=40 foot; warden def_foot=40.
    # A = 10*40*(100+0)//100 * Q // Q = 400
    # D_units = 10 * (40*Q//Q + 0) // Q * 1 = 10 * 40 = 400; wall=0 → D=400
    att = {(1, "brute"): 10}
    defs = {(2, "warden"): 10}
    r = _battle(att, defs)
    assert r.A == r.D  # tie
    assert r.attacker_won is False  # ties go to defender
    # x = pow15(A, D) = pow15(A, A) = Q → loser loses all
    assert r.att_losses[(1, "brute")] == 10
    assert r.att_loss_q == Q


def test_tie_raid_mode_fifty_fifty():
    # Same tie scenario, raid mode
    att = {(1, "brute"): 100}
    defs = {(2, "warden"): 100}
    r = _battle(att, defs, raid=True)
    assert r.A == r.D
    # x = Q → winner frac = Q*Q//(Q+Q) = Q//2, loser frac = Q*Q//(Q+Q) = Q//2
    # So both sides lose ~50%.
    # att is loser, loses loser_frac = Q*Q//(Q+Q)
    total_att_lost = sum(r.att_losses.values())
    total_def_lost = sum(r.def_losses.values())
    assert abs(total_att_lost - 50) <= 1
    assert abs(total_def_lost - 50) <= 1


# ---------------------------------------------------------------------------
# A=0 raises ValueError
# ---------------------------------------------------------------------------


def test_zero_attack_raises():
    # scouts only (cls="-") → raw_atk=0 → A=0
    att = {(1, "scout"): 10}
    defs = {(2, "warden"): 5}
    with pytest.raises(ValueError):
        _battle(att, defs)


# ---------------------------------------------------------------------------
# D=0 (empty defenders) → attacker loses 0
# ---------------------------------------------------------------------------


def test_empty_defenders_attacker_wins_no_losses():
    att = {(1, "brute"): 20}
    r = _battle(att, {})
    assert r.attacker_won is True
    assert sum(r.att_losses.values()) == 0
    assert r.D == 0


# ---------------------------------------------------------------------------
# Armor changes D
# ---------------------------------------------------------------------------


def test_armor_increases_defense():
    att = {(1, "brute"): 50}
    defs = {(2, "bulwark"): 20}
    r_no_armor = _battle(att, defs)
    r_with_armor = _battle(att, defs, armor={2: 5})
    assert r_with_armor.D > r_no_armor.D


def test_per_owner_armor():
    # Two defender owners; only one has armor
    att = {(1, "brute"): 50}
    defs = {(2, "bulwark"): 10, (3, "bulwark"): 10}
    r_base = _battle(att, defs)
    r_arm = _battle(att, defs, armor={2: 5})
    assert r_arm.D > r_base.D


# ---------------------------------------------------------------------------
# Wall formula
# ---------------------------------------------------------------------------


def test_wall_increases_defense():
    att = {(1, "brute"): 10}
    defs = {(2, "warden"): 10}
    r0 = _battle(att, defs, wall=0)
    r5 = _battle(att, defs, wall=5)
    assert r5.D > r0.D


def test_wall_formula_exact():
    # D = (D_units + 50*wall) * (100 + 4*wall) // 100
    # With 10 wardens (def_foot=40) pure foot attack, wall=3:
    # D_units = 10 * 40 = 400; D = (400 + 150) * 112 // 100 = 550*112//100 = 616
    att = {(1, "brute"): 10}
    defs = {(2, "warden"): 10}
    r = _battle(att, defs, wall=3)
    assert r.D == (400 + 50 * 3) * (100 + 4 * 3) // 100


# ---------------------------------------------------------------------------
# Class-mix weighting
# ---------------------------------------------------------------------------


def test_class_mix_affects_defense():
    # Pure foot vs bulwark (def_foot=130 > def_swift=110) → foot gives higher D
    # Pure swift vs bulwark (def_swift=110) → lower D
    defs = {(2, "bulwark"): 60}
    att_foot = {(1, "brute"): 250}    # brute: cls=foot, atk=40
    att_swift = {(1, "outrider"): 250}  # outrider: cls=swift, atk=55
    r_foot = _battle(att_foot, defs)
    r_swift = _battle(att_swift, defs)
    # bulwark def_foot=130 > def_swift=110, so pure foot attackers produce higher D
    assert r_foot.D > r_swift.D


# ---------------------------------------------------------------------------
# apportion — largest remainder
# ---------------------------------------------------------------------------


def test_apportion_sums_to_want():
    stacks = {(1, "brute"): 50, (2, "warden"): 30}
    losses = apportion(stacks, Q // 2, round_up=True)
    # ceil((50+30)*0.5) = 40
    assert sum(losses.values()) == 40


def test_apportion_never_exceeds_stack():
    stacks = {(1, "brute"): 10, (2, "warden"): 3}
    losses = apportion(stacks, Q, round_up=True)
    for key, lost in losses.items():
        assert lost <= stacks[key]


def test_apportion_tie_order_by_owner_unit():
    # Equal stacks, equal remainder → tie broken by (owner_id, unit_id)
    stacks = {(2, "brute"): 5, (1, "warden"): 5}
    # want = ceil(10 * 0.3) = 3
    losses = apportion(stacks, 3 * Q // 10, round_up=True)
    # base for each: floor(5 * 0.3) = 1 each → sum=2; need to distribute 1 extra
    # tiebreak: (owner_id asc) → (1, "warden") gets the extra
    assert losses[(1, "warden")] == 2
    assert losses[(2, "brute")] == 1


def test_apportion_many_tiny_stacks_proportional():
    # 10 stacks of 3; total=30; frac=1/3 → want=ceil(10)=10 → each gets 1
    stacks = {(i, "brute"): 3 for i in range(10)}
    losses = apportion(stacks, Q // 3, round_up=True)
    assert sum(losses.values()) == 10
    for v in losses.values():
        assert v >= 1


def test_apportion_reinforcement_all_take_at_least_one_when_total_loss_geq_1():
    # Many tiny stacks; total loss >=1 means not all can be zero.
    # 20 stacks of 1; total=20; frac = Q//20 → want = 1
    stacks = {(i, "brute"): 1 for i in range(20)}
    losses = apportion(stacks, Q // 20, round_up=True)
    assert sum(losses.values()) == 1  # exactly 1 unit taken across all stacks


# ---------------------------------------------------------------------------
# morale_q
# ---------------------------------------------------------------------------


def test_morale_q_full_at_r_ge_half():
    # r = def/att >= 0.5 → morale = Q
    m = morale_q(1000, 1000)  # r=1
    assert m == Q

    m = morale_q(1000, 500)  # r=0.5
    assert m == Q


def test_morale_q_at_r_0_2():
    # r=0.2 → morale = clamp(0.3 + 1.4*0.2, ...) = clamp(0.58, ...) = 0.58
    m = morale_q(1000, 200)
    expected = 3 * Q // 10 + 14 * (200 * Q // 1000) // 10
    assert m == max(3 * Q // 10, min(Q, expected))
    # Check approximate value ≈ 0.58*Q
    assert 579_000_000 <= m <= 581_000_000


def test_morale_q_at_r_0_1():
    # r=0.1 → 0.3 + 1.4*0.1 = 0.44
    m = morale_q(1000, 100)
    assert 439_000_000 <= m <= 441_000_000


def test_morale_q_floor_0_3():
    # The floor (3*Q//10) is only reached when r_q rounds to 0,
    # which requires att > def*Q, i.e. att > 10*Q = 10^10.
    m = morale_q(10**11, 0)
    assert m == 3 * Q // 10


def test_morale_q_zero_military_floor():
    # Both zero → floor of max(0, 10) / max(0, 10) = 1 → Q
    m = morale_q(0, 0)
    assert m == Q


# ---------------------------------------------------------------------------
# allocate_loot
# ---------------------------------------------------------------------------


def test_allocate_loot_basic():
    # 100 ore exposed, 0 wood/gem; cargo=100 units, no bucket
    exposed = {"ore": 100_000, "wood": 0, "gem": 0}
    loot = allocate_loot(exposed, 100, None, {"ore": 1000, "wood": 1000, "gem": 2500})
    # E=100k; f_q = min(Q, 100*1000*Q//100000) = min(Q, Q) = Q
    assert loot["ore"] == 100_000
    assert loot["wood"] == 0


def test_allocate_loot_cargo_limited():
    exposed = {"ore": 200_000, "wood": 200_000, "gem": 0}
    # E=400k; cargo=100 units → f = 100*1000/400000 = 0.25
    loot = allocate_loot(exposed, 100, None, {"ore": 1000, "wood": 1000, "gem": 2500})
    assert loot["ore"] == 50_000
    assert loot["wood"] == 50_000


def test_allocate_loot_bucket_limited():
    exposed = {"ore": 100_000, "wood": 100_000, "gem": 0}
    # EV = 100k*1000//1000 + 100k*1000//1000 = 200k milli-value
    # bucket = 100k → f = min(..., 100k*Q//200k) = 0.5
    vpu = {"ore": 1000, "wood": 1000, "gem": 2500}
    loot = allocate_loot(exposed, 10_000, 100_000, vpu)
    assert loot["ore"] == 50_000
    assert loot["wood"] == 50_000


def test_allocate_loot_proportional():
    exposed = {"ore": 60_000, "wood": 40_000, "gem": 0}
    # E=100k; cargo=50 → f=50*1000/100000=0.5
    loot = allocate_loot(exposed, 50, None, {"ore": 1000, "wood": 1000, "gem": 2500})
    assert loot["ore"] == 30_000
    assert loot["wood"] == 20_000


def test_allocate_loot_zero_exposure():
    exposed = {"ore": 0, "wood": 0, "gem": 0}
    loot = allocate_loot(exposed, 100, None, {"ore": 1000, "wood": 1000, "gem": 2500})
    assert all(v == 0 for v in loot.values())


# ---------------------------------------------------------------------------
# resolve_scout
# ---------------------------------------------------------------------------


def test_scout_success_no_defenders():
    success, att_lost, def_lost = resolve_scout(10, 0, 0, 0)
    assert success is True
    assert att_lost == 0
    assert def_lost == 0


def test_scout_success():
    # 100 att scouts vs 10 def scouts, esp both 0
    # 100*(100) > 10*(100) → success
    success, att_lost, def_lost = resolve_scout(100, 10, 0, 0)
    assert success is True
    assert att_lost < 100
    assert def_lost <= 10


def test_scout_failure():
    # 5 att scouts vs 50 def scouts → failure
    success, att_lost, _def_lost = resolve_scout(5, 50, 0, 0)
    assert success is False
    assert att_lost == 5  # all die


def test_scout_esp_affects_outcome():
    # Without esp: 10 att vs 15 def → would fail
    # With esp_att=5: 10*(175) = 1750 vs 15*(100) = 1500 → success
    s1, _, _ = resolve_scout(10, 15, 0, 0)
    s2, _, _ = resolve_scout(10, 15, 5, 0)
    assert s1 is False
    assert s2 is True


# ---------------------------------------------------------------------------
# siege_levels
# ---------------------------------------------------------------------------


def test_siege_removes_levels():
    costs = [100, 200, 300, 400, 500]  # cost to build each level (1-indexed)
    # siege_value=300, current=3 → remove level 3 (cost 300) → 1 level
    removed = siege_levels(300, costs, 3, max_levels=3)
    assert removed == 1


def test_siege_removes_multiple():
    costs = [100, 200, 300, 400, 500]
    # siege=700, current=4 → remove L4(400): 300 left; remove L3(300): 0 left → 2 removed
    removed = siege_levels(700, costs, 4, max_levels=3)
    assert removed == 2


def test_siege_respects_max_levels():
    costs = [100, 100, 100, 100, 100]
    # siege=500, can afford all 5, but max=2
    removed = siege_levels(500, costs, 5, max_levels=2)
    assert removed == 2


def test_siege_never_below_zero():
    costs = [100]
    removed = siege_levels(1000, costs, 1, max_levels=3)
    assert removed == 1  # only 1 level exists


def test_siege_level_zero_no_removal():
    costs = [100, 200]
    removed = siege_levels(1000, costs, 0, max_levels=3)
    assert removed == 0


def test_siege_insufficient_value():
    costs = [500, 500]
    removed = siege_levels(300, costs, 2, max_levels=3)
    assert removed == 0


# ---------------------------------------------------------------------------
# Concentration property test (plans/outpost.md §6.7 sim T4 note)
# ---------------------------------------------------------------------------


def test_concentration_one_wave_attacker_wins():
    """250 brutes (all foot, atk=40) in one wave vs 60 bulwarks (def_foot=130).

    Attack mode. Attacker must win.
    """
    att = {(1, "brute"): 250}
    defs = {(2, "bulwark"): 60}
    r = _battle(att, defs)
    assert r.attacker_won is True


def test_concentration_ten_waves_attacker_loses():
    """250 brutes split into 10 waves of 25 (carrying defender losses).

    Each wave: attacker has 25 brutes vs surviving bulwarks.
    After all 10 waves: attacker loses all 250, >= 30 bulwarks survive.
    """
    defender_count = 60
    total_att_lost = 0
    att_remaining = 250

    for _ in range(10):
        if att_remaining <= 0 or defender_count <= 0:
            break
        wave_size = min(25, att_remaining)
        att = {(1, "brute"): wave_size}
        defs = {(2, "bulwark"): defender_count}
        r = _battle(att, defs)
        att_lost = sum(r.att_losses.values())
        def_lost = sum(r.def_losses.values())
        total_att_lost += att_lost
        att_remaining -= att_lost
        defender_count -= def_lost

    # All 250 attacker brutes should be lost
    assert att_remaining == 0
    # >= 30 bulwarks survive
    assert defender_count >= 30
