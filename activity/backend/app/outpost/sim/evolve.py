"""Evolutionary search for dominant strategies (exploit finder).

A population of ``Genome``s competes inside the default roster: each
candidate plays as a cohort of agents among the scripted archetypes, on the
same seeds. Fitness = the cohort's median net worth (value invested in
buildings and research plus living army value) ÷ the median net worth of
everyone else. Power alone would reward never building an army, because
power deliberately excludes units (§6.16). Elites survive; children come from uniform crossover and
Gaussian mutation within ``Genome.bounds()``. A best fitness above the
dominance threshold means the rules have a strategy that beats every
archetype — a balance bug to inspect.
"""
import logging
import random
import statistics
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, fields
from pathlib import Path

from ..rules.model import Params
from . import results
from .agents import ARCHETYPES, Genome
from .runner import DEFAULT_ROSTER, RosterEntry, run_round

logger = logging.getLogger(__name__)

DOMINANT_FITNESS = 1.3


@dataclass(frozen=True, slots=True)
class EvolveResult:
    """Outcome of a search."""

    evo_id: int
    best: Genome
    best_fitness: float
    history: list[tuple[float, float]]  # (best, median) per generation

    @property
    def dominant(self) -> bool:
        """True when a strategy beats the field by the dominance margin."""
        return self.best_fitness > DOMINANT_FITNESS


def net_worth(player: dict) -> float:
    """Value invested in buildings/research plus living units (value units)."""
    return player["final_power"] * 1000 + player["army_value"]


def evaluate(
    params: Params, genome: Genome, cohort: int, seed: int, quit_hours: float
) -> tuple[float, list[dict]]:
    """Play ``cohort`` agents of ``genome`` in the default field.

    Returns (fitness, the cohort's player results). Fitness is the cohort's
    median net worth over everyone else's median net worth.
    """
    roster = (*DEFAULT_ROSTER, RosterEntry("evolved", cohort, genome=genome))
    result = run_round(params, roster, seed, quit_hours=quit_hours)
    mine = [p for p in result.players if p["archetype"] == "evolved"]
    rest = [net_worth(p) for p in result.players if p["archetype"] != "evolved"]
    base = statistics.median(rest) if rest else 0.0
    worth = statistics.median([net_worth(p) for p in mine]) if mine else 0.0
    return (worth / base if base else 0.0), mine


def _fitness_job(args: tuple[Params, Genome, int, int, float]) -> float:
    return evaluate(*args)[0]


def _mutate(genome: Genome, rng: random.Random, sigma: float) -> Genome:
    bounds = Genome.bounds()
    values = {}
    for f in fields(Genome):
        lo, hi = bounds[f.name]
        v = getattr(genome, f.name) + rng.gauss(0, sigma * (hi - lo))
        values[f.name] = min(hi, max(lo, v))
    return Genome(**values)


def _crossover(a: Genome, b: Genome, rng: random.Random) -> Genome:
    return Genome(
        **{
            f.name: getattr(a if rng.random() < 0.5 else b, f.name)
            for f in fields(Genome)
        }
    )


def evolve(
    db_path: Path,
    *,
    generations: int = 8,
    population: int = 12,
    cohort: int = 4,
    seeds: tuple[int, ...] = (1, 2),
    params: Params | None = None,
    seed: int = 0,
    sigma: float = 0.15,
    workers: int = 0,
    quit_hours: float = 24.0,
) -> EvolveResult:
    """Run the search and store every generation."""
    params = params or Params()
    rng = random.Random(seed)
    pop: list[Genome] = list(ARCHETYPES.values())
    while len(pop) < population:
        pop.append(_mutate(rng.choice(list(ARCHETYPES.values())), rng, 0.4))
    pop = pop[:population]
    conn = results.connect(db_path)
    evo_id = results.next_evo_id(conn)
    history: list[tuple[float, float]] = []
    best: tuple[float, Genome] = (0.0, pop[0])
    with ProcessPoolExecutor(max_workers=workers or None) as pool:
        for gen in range(generations):
            jobs = [
                (params, g, cohort, s, quit_hours) for g in pop for s in seeds
            ]
            scores = list(pool.map(_fitness_job, jobs, chunksize=1))
            per = len(seeds)
            fitness = [
                statistics.mean(scores[i * per : (i + 1) * per])
                for i in range(len(pop))
            ]
            scored = sorted(
                zip(pop, fitness, strict=True), key=lambda gf: -gf[1]
            )
            results.save_generation(
                conn, evo_id, gen, [(g.to_json(), f) for g, f in scored]
            )
            gen_best = scored[0]
            history.append((gen_best[1], statistics.median(fitness)))
            if gen_best[1] > best[0]:
                best = (gen_best[1], gen_best[0])
            logger.info(
                "evo %d gen %d: best %.3f median %.3f",
                evo_id,
                gen,
                gen_best[1],
                history[-1][1],
            )
            elites = [g for g, _f in scored[: max(2, population // 4)]]
            children = list(elites)
            while len(children) < population:
                a, b = rng.sample(elites, 2)
                children.append(_mutate(_crossover(a, b, rng), rng, sigma))
            pop = children
    conn.close()
    return EvolveResult(evo_id, best[1], best[0], history)
