"""Jev plays Outpost: TypeSafe's System One model makes a player's calls.

Code stays in control (docs.typesafe.ai/concepts/how-to-build-with-system-one):
the scripted ``Brain`` still builds, trains, researches and computes every
legal option with the real combat formula. At each check-in Jev gets the
player's situation as state and answers up to four Choice questions in one
request (speculative fan-out — only relevant questions are asked):

- ``stance`` (first check-in of a day): spend little, normally or heavily
  on troops → the daily stance arm.
- ``priority`` (first check-in of a day): grow the economy, expand to a new
  base, or fortify → a genome tweak for the day.
- ``raid`` (when the home army has targets): pick one of up to five
  pre-scored targets, or none.
- ``response`` (when an attack is landing before the next check-in): hold
  or evacuate the army.

Answers are cached on disk by request hash, so a seed replays identically
and for free. Needs ``TYPESAFE_API_KEY`` (or a cache that already holds
every answer).
"""
import hashlib
import json
import logging
import os
import sqlite3
from dataclasses import dataclass, field, replace
from pathlib import Path

import httpx

from ..engine.state import Base, March, Player
from ..rules.model import BUILD_RES, DAY_MS, HOUR_MS, MILLI, value_m
from .agents import Agent, Brain, Genome
from .experience import API_KEY_ENV, API_URL, MODEL, TIMEOUT_S, JudgeError

logger = logging.getLogger(__name__)

MAX_TARGETS = 5
STANCES = ("economy", "balanced", "military")  # indexes match learning.STANCES

FRAME = (
    "You are a player in a casual 4-week online strategy game played in a "
    "Discord community. You check in four times a day. You want to finish "
    "the round as strong as possible without wasting your army."
)


class JevCache:
    """sqlite cache of Jev responses keyed by request hash."""

    def __init__(self, path: Path | None) -> None:
        self._mem: dict[str, dict] = {}
        self._conn: sqlite3.Connection | None = None
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(path)
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS jev_cache"
                " (key TEXT PRIMARY KEY, response TEXT)"
            )

    @staticmethod
    def key(payload: dict) -> str:
        """Stable hash of a request payload."""
        raw = json.dumps(payload, sort_keys=True).encode()
        return hashlib.sha256(raw).hexdigest()

    def get(self, key: str) -> dict | None:
        """Cached answers, if any."""
        if key in self._mem:
            return self._mem[key]
        if self._conn is None:
            return None
        row = self._conn.execute(
            "SELECT response FROM jev_cache WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        self._mem[key] = json.loads(row[0])
        return self._mem[key]

    def put(self, key: str, answers: dict) -> None:
        """Store answers."""
        self._mem[key] = answers
        if self._conn is not None:
            self._conn.execute(
                "INSERT OR REPLACE INTO jev_cache VALUES (?, ?)",
                (key, json.dumps(answers)),
            )
            self._conn.commit()


@dataclass(slots=True)
class DailyPlan:
    """Decisions that hold for a whole in-game day."""

    day: int
    stance: int
    priority: str


@dataclass(slots=True)
class JevController:
    """Makes an agent's key decisions with Jev (see module docstring)."""

    client: httpx.Client
    cache: JevCache = field(default_factory=lambda: JevCache(None))
    calls: int = 0
    cache_hits: int = 0
    log: list[dict] = field(default_factory=list)
    _daily: dict[int, DailyPlan] = field(default_factory=dict)

    @classmethod
    def from_env(cls, cache_path: Path | None = None) -> "JevController":
        """Client authenticated from ``TYPESAFE_API_KEY``."""
        key = os.environ.get(API_KEY_ENV, "").strip()
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        return cls(
            client=httpx.Client(headers=headers, timeout=TIMEOUT_S),
            cache=JevCache(cache_path),
        )

    # ----------------------------------------------------------- decide

    def decide(self, brain: Brain, agent: Agent, player: Player) -> Genome:
        """Ask Jev this check-in's questions; return today's genome."""
        home = brain.w.bases[player.base_ids[0]]
        day = brain.day()
        state = self._state(brain, player, home)
        questions: dict[str, dict] = {}
        daily = self._daily.get(agent.player_id)
        if daily is None or daily.day != day:
            questions["stance"] = _choice(
                "Considering your situation, how much of your spare "
                "resources should go into troops today?",
                {
                    "economy": "Spend little on troops; invest in buildings",
                    "balanced": "A normal share on troops",
                    "military": "Spend heavily on troops",
                },
            )
            questions["priority"] = _choice(
                "What should your main building focus be today?",
                {
                    "grow": "Upgrade mines, storage and research",
                    "expand": "Work toward founding an extra base",
                    "fortify": "Walls and defensive troops",
                },
            )
        targets = self._targets(brain, agent, player, home)
        if targets:
            state["raid_targets"] = {k: facts for k, (_t, facts) in targets.items()}
            questions["raid"] = _choice(
                "Your army is home. Which target in `raid_targets` should it "
                "raid now, if any? Predictions use the real battle rules.",
                {
                    **{k: f"Raid `raid_targets.{k}`" for k in targets},
                    "none": "Don't raid now; keep the army home",
                },
            )
        threats = brain.threats(agent, home)
        if threats:
            state["incoming_attacks"] = _threat_facts(brain, home, threats)
            questions["response"] = _choice(
                "Enemy attacks in `incoming_attacks` land before your next "
                "check-in. Keep your army home to fight, or move it out until "
                "they land? Stock above your vault may be looted either way.",
                {
                    "hold": "Keep the army home and defend",
                    "evacuate": "Move the army away until the attacks land",
                },
            )
        answers = self._ask(state, questions) if questions else {}
        if "stance" in answers:
            self._daily[agent.player_id] = DailyPlan(
                day,
                STANCES.index(answers["stance"]["choice"]),
                answers["priority"]["choice"],
            )
        daily = self._daily[agent.player_id]
        agent.plan["stance"] = daily.stance
        if "raid" in answers:
            pick = answers["raid"]["choice"]
            agent.plan["raid"] = {
                home.id: targets[pick][0] if pick in targets else 0
            }
        if "response" in answers:
            agent.plan["evacuate"] = answers["response"]["choice"] == "evacuate"
        t_h = brain.w.now_ms / HOUR_MS
        for qid, ans in answers.items():
            self.log.append(
                {
                    "t_h": t_h,
                    "player_id": agent.player_id,
                    "question": qid,
                    "choice": ans["choice"],
                    "confidence": ans.get("confidence", 0.0),
                }
            )
        return _genome_for(agent.genome, daily.priority, day)

    # ------------------------------------------------------------ state

    def _state(self, brain: Brain, player: Player, home: Base) -> dict:
        w, e = brain.w, brain.e
        ranked = sorted(
            (p for p in w.players.values() if p.status != "gone"),
            key=brain.net_worth,
            reverse=True,
        )
        rank = ranked.index(player) + 1
        hourly = e.hourly_value(player) / MILLI
        stock = sum(
            value_m({r: w.bases[b].stock[r] for r in BUILD_RES})
            for b in player.base_ids
        ) / MILLI
        day_ago = w.now_ms - DAY_MS
        hits = [
            x
            for x in w.loot_log
            if x.defender == player.id and x.t_ms >= day_ago
        ]
        alliance = w.alliances.get(player.alliance_id or 0)
        site = next(
            (
                s
                for s in w.sites.values()
                if alliance is not None and s.alliance_id == alliance.id
            ),
            None,
        )
        return {
            "game": FRAME,
            "day": f"{brain.day() + 1} of {w.rules.params.round_days}",
            "your_rank_by_net_worth": f"{rank} of {len(ranked)}",
            "your_production_per_hour": round(hourly),
            "your_stock": round(stock),
            "your_home_army_value": round(
                brain._unit_value(home.garrison) / MILLI
            ),
            "your_wall_level": home.buildings.get("wall", 0),
            "your_bases": len(player.base_ids),
            "times_you_were_raided_last_24h": len(hits),
            "stock_lost_last_24h_in_hours_of_production": round(
                sum(x.value_m for x in hits) / MILLI / max(1.0, hourly), 1
            ),
            "in_alliance": (
                f"yes, {len(alliance.members)} members" if alliance else "no"
            ),
            "alliance_monument_level": site.level if site else None,
        }

    def _targets(
        self, brain: Brain, agent: Agent, player: Player, home: Base
    ) -> dict[str, tuple[int, dict]]:
        party, options = brain.raid_options(agent, player, home)
        options.sort(key=lambda o: -o[0])
        ranked = sorted(
            (p for p in brain.w.players.values() if p.status != "gone"),
            key=brain.net_worth,
            reverse=True,
        )
        out: dict[str, tuple[int, dict]] = {}
        for i, (_score, target, est) in enumerate(options[:MAX_TARGETS], 1):
            profit, ratio = est
            hours = (
                brain.e.travel_ms(player, party, home, (target.x, target.y))
                / HOUR_MS
            )
            owner = brain.w.players.get(target.owner or 0)
            if target.kind == "player" and owner in ranked:
                what = (
                    "another player, ranked "
                    f"{ranked.index(owner) + 1} of {len(ranked)}"
                )
            else:
                what = f"computer-run camp, tier {target.tier} of 5"
            seen = agent.memory.seen.get(target.id, 0)
            out[f"t{i}"] = (
                target.id,
                {
                    "target": what,
                    "travel_hours_one_way": round(hours, 1),
                    "predicted_profit": round(profit / MILLI),
                    "predicted_profit_pct_of_army_value": round(100 * ratio),
                    "your_past_raids_here": seen,
                    "past_average_return_pct": (
                        round(100 * agent.memory.ema[target.id])
                        if seen
                        else None
                    ),
                },
            )
        return out

    # -------------------------------------------------------------- API

    def _ask(self, state: dict, questions: dict) -> dict[str, dict]:
        payload = {"state": state, "model": MODEL, "questions": questions}
        key = JevCache.key(payload)
        cached = self.cache.get(key)
        if cached is not None:
            self.cache_hits += 1
            return cached
        try:
            response = self.client.post(API_URL, json=payload)
        except httpx.HTTPError as exc:
            raise JudgeError(f"TypeSafe request failed: {exc}") from exc
        if response.status_code != 200:
            raise JudgeError(
                f"TypeSafe returned {response.status_code}:"
                f" {response.text[:200]}"
            )
        self.calls += 1
        answers = response.json()["answers"]
        self.cache.put(key, answers)
        return answers


def decision_metrics(log: list[dict]) -> dict[str, float]:
    """Share of each answer per question, e.g. ``jev_raid_none_share``."""
    counts: dict[str, dict[str, int]] = {}
    for d in log:
        q = counts.setdefault(d["question"], {})
        q[d["choice"]] = q.get(d["choice"], 0) + 1
    out = {"jev_decisions": float(len(log))}
    for question, choices in counts.items():
        total = sum(choices.values())
        for choice, n in choices.items():
            out[f"jev_{question}_{choice}_share"] = n / total
    return out


def _genome_for(genome: Genome, priority: str, day: int) -> Genome:
    if priority == "expand":
        return replace(genome, expand_day=float(day))
    if priority == "fortify":
        return replace(
            genome, defense_ratio=1.0, wall_weight=max(genome.wall_weight, 0.8)
        )
    return genome


def _threat_facts(brain: Brain, home: Base, threats: list[March]) -> dict:
    sees = home.buildings.get("tower", 0) >= 7
    now = brain.w.now_ms
    return {
        "count": len(threats),
        "first_lands_in_hours": round(
            (min(m.arrive_ms for m in threats) - now) / HOUR_MS, 1
        ),
        "attacker_army_value": (
            round(sum(brain._unit_value(m.units) for m in threats) / MILLI)
            if sees
            else "unknown (your watchtower is too low to see sizes)"
        ),
    }


def _choice(instructions: str, criteria: dict[str, str]) -> dict:
    return {"type": "choice", "instructions": instructions, "criteria": criteria}
