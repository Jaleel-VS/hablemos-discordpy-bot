"""In-round learning for simulated players.

Two small learners, both deterministic given the seeded RNG:

- ``Bandit``: epsilon-greedy over a few discrete *stances* (how hard to
  push the army). Each local day a player commits to one arm; at the next
  day it is scored by how much its net worth grew relative to the field,
  so the late-round slowdown everyone shares doesn't punish later arms.
- ``TargetMemory``: an exponential moving average of the realised raid
  return (loot minus losses, over the party's value) per target base, so
  players learn which camps pay and which neighbours fight back.
"""
import math
import random
from dataclasses import dataclass, field

STANCES = (0.5, 1.0, 1.6)  # army_share multipliers
EMA_ALPHA = 0.4


@dataclass(slots=True)
class Bandit:
    """Epsilon-greedy multi-armed bandit with incremental means."""

    arms: tuple[float, ...] = STANCES
    counts: list[int] = field(default_factory=list)
    means: list[float] = field(default_factory=list)
    current: int = 1
    started_worth: float = 0.0
    started_field: float = 0.0
    started_day: int = -1
    days_used: list[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        n = len(self.arms)
        self.counts = self.counts or [0] * n
        self.means = self.means or [0.0] * n
        self.days_used = self.days_used or [0] * n

    def update(self, reward: float) -> None:
        """Credit the current arm with a reward."""
        i = self.current
        self.counts[i] += 1
        self.means[i] += (reward - self.means[i]) / self.counts[i]

    def choose(self, rng: random.Random, epsilon: float) -> int:
        """Untried arms first, then explore with prob ``epsilon``."""
        untried = [i for i, c in enumerate(self.counts) if c == 0]
        if untried:
            self.current = untried[0]
        elif rng.random() < epsilon:
            self.current = rng.randrange(len(self.arms))
        else:
            best = max(self.means)
            self.current = self.means.index(best)
        self.days_used[self.current] += 1
        return self.current

    @property
    def multiplier(self) -> float:
        """Army-share multiplier for the current arm."""
        return self.arms[self.current]


@dataclass(slots=True)
class TargetMemory:
    """EMA of realised raid return per target base id."""

    ema: dict[int, float] = field(default_factory=dict)
    seen: dict[int, int] = field(default_factory=dict)

    def record(self, target: int, ratio: float) -> None:
        """Fold one raid outcome (profit / party value) into the average."""
        prev = self.ema.get(target)
        self.ema[target] = (
            ratio if prev is None else prev + EMA_ALPHA * (ratio - prev)
        )
        self.seen[target] = self.seen.get(target, 0) + 1

    def blend(self, target: int, predicted: float, adapt: float) -> float:
        """Mix a predicted return with experience (weight ``adapt``)."""
        learned = self.ema.get(target)
        if learned is None:
            return predicted
        return (1 - adapt) * predicted + adapt * learned


def softmax_pick(
    scores: list[float], temperature: float, rng: random.Random
) -> int:
    """Index of the chosen option; greedy when ``temperature`` is ~0."""
    if not scores:
        raise ValueError("no options")
    best = max(range(len(scores)), key=lambda i: scores[i])
    if temperature <= 1e-6:
        return best
    top = scores[best]
    weights = [math.exp((s - top) / temperature) for s in scores]
    return rng.choices(range(len(scores)), weights=weights)[0]
