"""Mutable world state for one Outpost round.

The engine (``core.py``) is the only code that mutates these objects. State
holds no clock and no randomness: time is integer milliseconds since round
start and every change happens inside an engine call (plans/outpost.md §7).
"""
from dataclasses import dataclass, field

from ..rules.model import RESOURCES, Ruleset


@dataclass(slots=True)
class LaneItem:
    """A queued build, training batch, or research job."""

    id: int
    lane: str  # build | train | research
    item: str  # building, unit, or tech id
    amount: int  # target level (build/research) or unit count (train)
    base_id: int
    start_ms: int
    end_ms: int


@dataclass(slots=True)
class Membership:
    """One stint in an alliance (history kept for affiliation rules)."""

    alliance_id: int
    joined_ms: int
    left_ms: int | None = None


@dataclass(slots=True)
class Player:
    """A Discord user's participation in a round."""

    id: int
    joined_ms: int
    protection_until: int
    last_seen_ms: int
    status: str = "active"  # active | inactive | gone
    research: dict[str, int] = field(default_factory=dict)
    research_item: LaneItem | None = None
    spent_value_m: int = 0
    bucket_m: int = 0
    bucket_res: int = 0
    bucket_ms: int = 0
    catchup_pct: int = 0
    catchup_until: int = 0
    vacation_state: str = "none"  # none | pending | active
    vacation_at: int = 0  # activation (pending) or start (active)
    vacation_used_ms: int = 0
    vacation_cooldown_until: int = 0
    last_hostile_launch_ms: int = -(10**15)
    attacked: dict[int, int] = field(default_factory=dict)
    alliance_id: int | None = None
    memberships: list[Membership] = field(default_factory=list)
    hop_cooldown_until: int = 0
    invites: set[int] = field(default_factory=set)
    base_ids: list[int] = field(default_factory=list)
    reserved_slots: int = 0
    inactivity_version: int = 0

    @property
    def power(self) -> int:
        """Public score: value spent on buildings and research ÷ 1000."""
        return self.spent_value_m // 1_000_000


@dataclass(slots=True)
class Base:
    """A tile with stock: player base, NPC camp, tutorial camp, or site."""

    id: int
    owner: int | None
    kind: str  # player | camp | tutorial | site
    x: int
    y: int
    tier: int
    stock: dict[str, int]
    settled_ms: int
    buildings: dict[str, int] = field(default_factory=dict)
    garrison: dict[str, int] = field(default_factory=dict)
    away: dict[str, int] = field(default_factory=dict)  # homed units in marches
    residual: dict[str, int] = field(
        default_factory=lambda: dict.fromkeys(RESOURCES, 0)
    )
    build_queue: list[LaneItem] = field(default_factory=list)
    train_queue: list[LaneItem] = field(default_factory=list)
    rate_version: int = 0
    full: bool = True  # camps: False while a respawn is pending
    converted_ms: int | None = None  # camps converted from a gone player
    removed: bool = False


@dataclass(slots=True)
class March:
    """Units away from home (a stationed march is a reinforcement)."""

    id: int
    owner: int
    home_base: int
    mission: str  # raid|attack|reinforce|scout|transport|settle|contribute
    units: dict[str, int]
    cargo: dict[str, int]
    target_base: int | None
    target_xy: tuple[int, int]
    depart_ms: int
    arrive_ms: int
    return_ms: int = 0
    status: str = "outbound"  # outbound | stationed | returning | done
    outcome: str = ""


@dataclass(slots=True)
class Alliance:
    """Up to ``alliance_cap`` players with roles."""

    id: int
    name: str
    tag: str
    leader: int
    officers: set[int] = field(default_factory=set)
    members: set[int] = field(default_factory=set)


@dataclass(slots=True)
class Site:
    """Monument site state (§6.15); lives with the site base."""

    base_id: int
    alliance_id: int | None = None
    state: str = "npc"  # npc | owned | building
    level: int = 0
    contributed: dict[str, int] = field(
        default_factory=lambda: {"ore": 0, "wood": 0, "gem": 0}
    )
    build_end_ms: int = 0
    level_reached_ms: int = 0
    hold_until: int = 0
    version: int = 0


@dataclass(slots=True)
class LootEntry:
    """One successful loot against a player (for the P2 invariant)."""

    t_ms: int
    defender: int
    attacker: int
    value_m: int
    defender_hourly_value_m: int


@dataclass(slots=True)
class World:
    """All state of one round."""

    rules: Ruleset
    radius: int
    end_ms: int
    now_ms: int = 0
    seq: int = 0
    next_id: int = 1
    players: dict[int, Player] = field(default_factory=dict)
    bases: dict[int, Base] = field(default_factory=dict)
    tiles: dict[tuple[int, int], int] = field(default_factory=dict)
    marches: dict[int, March] = field(default_factory=dict)
    alliances: dict[int, Alliance] = field(default_factory=dict)
    sites: dict[int, Site] = field(default_factory=dict)
    events: list[tuple[int, int, str, tuple[int, ...]]] = field(
        default_factory=list
    )
    qualified_alliances: int = 0
    winner_alliance: int | None = None
    ended: bool = False
    loot_log: list[LootEntry] = field(default_factory=list)
    reports: list[dict] = field(default_factory=list)
    keep_reports: bool = False
    finished_marches: list[March] = field(default_factory=list)
    keep_marches: bool = False

    def new_id(self) -> int:
        """Next unique id for any entity."""
        value = self.next_id
        self.next_id += 1
        return value
