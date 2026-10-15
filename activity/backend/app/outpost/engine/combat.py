"""Outpost combat engine (see plans/outpost.md §6.7–6.10, §6.7.1).

All arithmetic is integer-only; no ``float`` on any runtime path.
``Q = 10**9`` is the fixed-point denominator.
"""

import math
from dataclasses import dataclass

from app.outpost.engine.fixed import Q, pow15

StackKey = tuple[int, str]  # (owner_id, unit_id); owner_id 0 = NPC


@dataclass(frozen=True, slots=True)
class UnitStats:
    """Subset of ``UnitDef`` required by the combat engine.

    See plans/outpost.md §6.3.
    """

    atk: int
    cls: str  # "foot" | "swift" | "-"
    def_foot: int
    def_swift: int
    cargo: int
    value_m: int  # milli-value per unit


@dataclass(frozen=True, slots=True)
class BattleResult:
    """Outcome of a single battle resolution (plans/outpost.md §6.7).

    ``att_loss_q`` / ``def_loss_q`` are fixed-point fractions (``[0, Q]``).
    """

    attacker_won: bool
    A: int  # effective attack (integer, after arms + morale)
    D: int  # effective defense (integer, after armor + wall)
    att_losses: dict[StackKey, int]
    def_losses: dict[StackKey, int]
    att_loss_q: int  # fraction of attacker side lost
    def_loss_q: int  # fraction of defender side lost


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _total(stacks: dict[StackKey, int]) -> int:
    """Sum all unit counts in *stacks*."""
    return sum(stacks.values())


def apportion(
    stacks: dict[StackKey, int],
    frac_q: int,
    round_up: bool,
) -> dict[StackKey, int]:
    """Distribute losses across stacks using the largest-remainder method.

    See plans/outpost.md §6.7.

    Parameters
    ----------
    stacks:
        Map of ``StackKey`` to count; values must be non-negative.
    frac_q:
        Fixed-point fraction of losses (``[0, Q]``).
    round_up:
        If ``True`` the loser's total is ``ceil(total*frac/Q)``; the winner's
        total uses ``floor``.

    Returns
    -------
    dict[StackKey, int]
        Per-stack loss counts (each capped at the stack size).
    """
    total = _total(stacks)
    if total == 0:
        return {}

    raw_want = total * frac_q
    want = (raw_want + Q - 1) // Q if round_up else raw_want // Q

    # Base allocation: floor(n_k * frac / Q)
    base: dict[StackKey, int] = {}
    remainders: list[tuple[int, StackKey]] = []
    base_sum = 0
    for key, n in stacks.items():
        raw = n * frac_q
        b = raw // Q
        # cap to stack size
        b = min(b, n)
        base[key] = b
        base_sum += b
        rem = raw - b * Q  # remainder numerator
        remainders.append((-rem, key))  # negate for descending sort

    extra = want - base_sum
    # Sort by (remainder desc, owner_id asc, unit_id asc)
    remainders.sort(key=lambda t: (t[0], t[1][0], t[1][1]))

    result = dict(base)
    for i, (_, key) in enumerate(remainders):
        if i >= extra:
            break
        n = stacks[key]
        if result[key] < n:
            result[key] += 1

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def morale_q(att_military: int, def_military: int) -> int:
    """Return morale as a fixed-point fraction ``[3*Q//10, Q]``.

    See plans/outpost.md §6.8.

    ``r = max(def, 10) / max(att, 10)``
    ``morale = clamp(0.3 + 1.4*r, 0.3, 1.0)``

    The zero-military floor ensures the result is always ``>= 10*Q//100``
    even when both sides have no military.
    """
    att = max(att_military, 10)
    def_ = max(def_military, 10)
    r_q = def_ * Q // att
    raw = 3 * Q // 10 + 14 * r_q // 10
    lo = 3 * Q // 10
    return max(lo, min(Q, raw))


def resolve_battle(
    attackers: dict[StackKey, int],
    defenders: dict[StackKey, int],
    stats: dict[str, UnitStats],
    *,
    arms_level: int,
    armor_by_owner: dict[int, int],
    wall: int,
    morale_q: int,
    raid: bool,
) -> BattleResult:
    """Resolve a battle and return the full outcome.

    See plans/outpost.md §6.7.

    Parameters
    ----------
    attackers / defenders:
        ``{(owner_id, unit_id): count}`` snapshots at arrival.
    stats:
        ``{unit_id: UnitStats}`` for every unit type referenced.
    arms_level:
        Attacker's ``arms`` research level.
    armor_by_owner:
        Defender-side ``armor`` research level per owner (0 if absent).
    wall:
        Wall level at the target base.
    morale_q:
        Pre-computed morale in fixed point (call :func:`morale_q` separately).
    raid:
        ``True`` for raid mode; ``False`` for attack mode.

    Raises
    ------
    ValueError
        If effective attack ``A <= 0``.
    """
    # --- Compute A ---
    a_foot = sum(
        stats[uid].atk * n
        for (_, uid), n in attackers.items()
        if stats[uid].cls == "foot"
    )
    a_swift = sum(
        stats[uid].atk * n
        for (_, uid), n in attackers.items()
        if stats[uid].cls == "swift"
    )
    raw_atk = a_foot + a_swift
    A = raw_atk * (100 + 3 * arms_level) // 100 * morale_q // Q

    if A <= 0:
        raise ValueError(
            f"Effective attack A={A} <= 0; mission must be rejected at launch."
        )

    # --- Compute D ---
    mix_f_q = Q // 2 if raw_atk == 0 else a_foot * Q // raw_atk

    d_units = 0
    for (owner_id, uid), n in defenders.items():
        s = stats[uid]
        base_def = (s.def_foot * mix_f_q + s.def_swift * (Q - mix_f_q)) // Q
        armor = armor_by_owner.get(owner_id, 0)
        d_units += n * base_def * (100 + 3 * armor) // 100

    D = (d_units + 50 * wall) * (100 + 4 * wall) // 100

    # --- Outcome ---
    attacker_won = A > D

    if attacker_won:
        # x = (D/A)^1.5; but D may be 0 → x = 0
        x = pow15(D, A) if D > 0 else 0
    else:
        # defender wins (ties go to defender); A > 0 already guaranteed
        x = pow15(A, D) if D > 0 else Q  # D==0 impossible when defender wins

    if raid:
        # winner loses x/(1+x) = x*Q//(Q+x), loser loses Q/(1+x) = Q*Q//(Q+x)
        denom = Q + x
        winner_frac = x * Q // denom
        loser_frac = Q * Q // denom
    else:
        # attack mode: winner loses x, loser loses Q (all)
        winner_frac = x
        loser_frac = Q

    if attacker_won:
        att_loss_q = winner_frac
        def_loss_q = loser_frac
    else:
        att_loss_q = loser_frac
        def_loss_q = winner_frac

    # Loser rounds up; winner rounds down
    att_losses = apportion(
        attackers, att_loss_q, round_up=not attacker_won
    )
    def_losses = apportion(
        defenders, def_loss_q, round_up=attacker_won
    )

    return BattleResult(
        attacker_won=attacker_won,
        A=A,
        D=D,
        att_losses=att_losses,
        def_losses=def_losses,
        att_loss_q=att_loss_q,
        def_loss_q=def_loss_q,
    )


def allocate_loot(
    exposed_m: dict[str, int],
    cargo_units: int,
    bucket_value_m: int | None,
    value_per_unit: dict[str, int],
) -> dict[str, int]:
    """Compute milli-units looted per resource.

    See plans/outpost.md §6.9.

    Parameters
    ----------
    exposed_m:
        Per build-resource exposed stock in milli-units.
        ``e_r = floor(max(0, stock - vault) / 2)`` is computed by the caller.
    cargo_units:
        Surviving cargo capacity of the raiding army (units, not milli-units).
    bucket_value_m:
        Current loot-bucket fill in milli-value (``None`` skips bucket cap).
    value_per_unit:
        Trade value in milli-value per unit for each resource (e.g.
        ``{"ore": 1000, "wood": 1000, "gem": 2500}``).

    Returns
    -------
    dict[str, int]
        Milli-units taken per resource.
    """
    E = sum(exposed_m.values())
    if E == 0:
        return {r: 0 for r in exposed_m}

    # Milli-value of all exposed stock
    EV = sum(exposed_m[r] * value_per_unit[r] // 1000 for r in exposed_m)

    # f_q = min(Q, cargo_units*1000*Q // E [, bucket*Q // EV])
    f_q = min(Q, cargo_units * 1000 * Q // E)
    if bucket_value_m is not None and EV > 0:
        f_q = min(f_q, bucket_value_m * Q // EV)

    return {r: exposed_m[r] * f_q // Q for r in exposed_m}


def resolve_scout(
    att_scouts: int,
    def_scouts: int,
    esp_att: int,
    esp_def: int,
) -> tuple[bool, int, int]:
    """Resolve a scouting action.

    See plans/outpost.md §6.10.

    Returns
    -------
    tuple[bool, int, int]
        ``(success, att_lost, def_lost)``
    """
    if def_scouts == 0:
        return True, 0, 0

    success = att_scouts * (100 + 15 * esp_att) > def_scouts * (100 + 15 * esp_def)

    if success:
        # Attacker is winner; x = pow15(D, A) where D=def_scouts, A=att_scouts
        x = pow15(def_scouts, att_scouts) if att_scouts > 0 else Q
        # attacker (winner) loses floor(att * x/(1+x))
        # defender (loser)  loses ceil(def * 1/(1+x))
        denom = Q + x
        att_lost = att_scouts * x // denom  # floor
        def_lost = math.ceil(def_scouts * Q / denom) if denom > 0 else 0
        # integer version of ceil: (def_scouts * Q + denom - 1) // denom
        def_lost = (def_scouts * Q + denom - 1) // denom
    else:
        # All attacker scouts die; defender loses floor(def * x/(1+x))
        # x = pow15(A, D) where A=att_scouts, D=def_scouts
        x = pow15(att_scouts, def_scouts) if def_scouts > 0 else 0
        att_lost = att_scouts
        denom = Q + x
        def_lost = def_scouts * x // denom  # floor

    return success, att_lost, def_lost


def siege_levels(
    siege_value_m: int,
    level_costs_value_m: list[int],
    current_level: int,
    max_levels: int,
) -> int:
    """Return number of wall/monument levels removed by siege.

    See plans/outpost.md §6.7.1.

    Removes top levels while ``siege_value_m >= cost of that level``,
    up to ``max_levels`` total, never below level 0.

    Parameters
    ----------
    siege_value_m:
        Total siege value in milli-value (surviving rams × ram value_m).
    level_costs_value_m:
        Cost in milli-value for each level; index is ``level - 1``
        (``level_costs_value_m[0]`` = cost to build level 1).
    current_level:
        Current wall / monument level.
    max_levels:
        Maximum levels that may be removed in one battle.

    Returns
    -------
    int
        Number of levels removed (0 if none).
    """
    removed = 0
    remaining = siege_value_m
    level = current_level

    while removed < max_levels and level > 0:
        cost = level_costs_value_m[level - 1]
        if remaining < cost:
            break
        remaining -= cost
        level -= 1
        removed += 1

    return removed
