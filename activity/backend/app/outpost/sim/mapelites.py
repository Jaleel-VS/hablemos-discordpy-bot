"""MAP-Elites: map which *styles* of play work, not just the single best.

The archive is a grid over two behaviour descriptors measured from what a
strategy actually did in its rounds (not from its genome), e.g. "share of
income from raiding players" × "share of net worth held as army". Each cell
keeps the fittest genome that landed there. Children are mutated copies
(sometimes crossed) of random elites; a child replaces a cell's elite only
when it is fitter. The result shows which styles are viable (fitness ≈ 1),
dead (< 1 or empty) or broken (> 1.3, see ``evolve.DOMINANT_FITNESS``).
"""
import json
import logging
import random
import statistics
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field, fields
from datetime import UTC, datetime
from pathlib import Path

from ..rules.model import Params
from . import results
from .agents import ARCHETYPES, Genome
from .evolve import _crossover, _mutate, evaluate, net_worth

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Descriptor:
    """A behaviour axis computed from a cohort's player results."""

    label: str
    max: float
    measure: Callable[[list[dict]], float]


def _median(values: list[float]) -> float:
    return statistics.median(values) if values else 0.0


DESCRIPTORS: dict[str, Descriptor] = {
    "loot_share": Descriptor(
        "income from raiding (camps + players)",
        0.5,
        lambda ps: _median([p["loot_income_share"] for p in ps]),
    ),
    "raid_share": Descriptor(
        "income from raiding players",
        0.05,  # the loot bucket keeps this small (§6.9)
        lambda ps: _median([p["raid_income_share"] for p in ps]),
    ),
    "army_frac": Descriptor(
        "net worth held as army",
        0.6,
        lambda ps: _median(
            [p["army_value"] / max(1e-9, net_worth(p)) for p in ps]
        ),
    ),
    "bases": Descriptor(
        "bases owned at round end",
        4.0,
        lambda ps: _median([float(p["bases"]) for p in ps]),
    ),
    "dodges": Descriptor(
        "dodges per player",
        40.0,
        lambda ps: _median([float(p["dodges"]) for p in ps]),
    ),
}


@dataclass(slots=True)
class Elite:
    """One archive cell's occupant."""

    genome: Genome
    fitness: float
    desc: tuple[float, float]
    found_at: int


@dataclass(slots=True)
class Archive:
    """Grid of elites keyed by (cell_x, cell_y)."""

    x_bins: int
    y_bins: int
    x_max: float
    y_max: float
    cells: dict[tuple[int, int], Elite] = field(default_factory=dict)

    def cell(self, desc: tuple[float, float]) -> tuple[int, int]:
        """Bin a descriptor pair; values past the max land in the top bin."""
        cx = int(desc[0] / self.x_max * self.x_bins)
        cy = int(desc[1] / self.y_max * self.y_bins)
        return (
            min(self.x_bins - 1, max(0, cx)),
            min(self.y_bins - 1, max(0, cy)),
        )

    def insert(self, elite: Elite) -> bool:
        """Keep ``elite`` if its cell is empty or it is fitter."""
        key = self.cell(elite.desc)
        current = self.cells.get(key)
        if current is not None and current.fitness >= elite.fitness:
            return False
        self.cells[key] = elite
        return True

    @property
    def coverage(self) -> float:
        """Share of cells filled."""
        return len(self.cells) / (self.x_bins * self.y_bins)

    @property
    def qd_score(self) -> float:
        """Sum of elite fitness (quality-diversity score)."""
        return sum(e.fitness for e in self.cells.values())


@dataclass(frozen=True, slots=True)
class MapResult:
    """Outcome of a MAP-Elites run."""

    me_id: int
    archive: Archive
    evaluations: int


def _job(
    args: tuple[Params, Genome, int, tuple[int, ...], float, str, str],
) -> tuple[Genome, float, tuple[float, float]]:
    params, genome, cohort, seeds, quit_hours, x_name, y_name = args
    fits, xs, ys = [], [], []
    for seed in seeds:
        fitness, players = evaluate(params, genome, cohort, seed, quit_hours)
        fits.append(fitness)
        xs.append(DESCRIPTORS[x_name].measure(players))
        ys.append(DESCRIPTORS[y_name].measure(players))
    return genome, statistics.mean(fits), (
        statistics.mean(xs),
        statistics.mean(ys),
    )


def _random_genome(rng: random.Random) -> Genome:
    bounds = Genome.bounds()
    return Genome(
        **{f.name: rng.uniform(*bounds[f.name]) for f in fields(Genome)}
    )


def run_map_elites(
    db_path: Path,
    *,
    x_name: str = "loot_share",
    y_name: str = "army_frac",
    bins: int = 8,
    initial: int = 24,
    iterations: int = 8,
    batch: int = 16,
    cohort: int = 4,
    seeds: tuple[int, ...] = (1, 2),
    params: Params | None = None,
    seed: int = 0,
    sigma: float = 0.15,
    workers: int = 0,
    quit_hours: float = 24.0,
) -> MapResult:
    """Fill the archive and store it; returns the archive."""
    if x_name not in DESCRIPTORS or y_name not in DESCRIPTORS:
        raise ValueError(f"descriptors must be one of {sorted(DESCRIPTORS)}")
    params = params or Params()
    rng = random.Random(seed)
    xd, yd = DESCRIPTORS[x_name], DESCRIPTORS[y_name]
    archive = Archive(bins, bins, xd.max, yd.max)
    evaluations = 0

    def submit(pool: ProcessPoolExecutor, genomes: list[Genome]) -> None:
        nonlocal evaluations
        jobs = [
            (params, g, cohort, seeds, quit_hours, x_name, y_name)
            for g in genomes
        ]
        for genome, fitness, desc in pool.map(_job, jobs, chunksize=1):
            archive.insert(Elite(genome, fitness, desc, evaluations))
            evaluations += 1

    with ProcessPoolExecutor(max_workers=workers or None) as pool:
        first = list(ARCHETYPES.values())
        first += [_random_genome(rng) for _ in range(max(0, initial - len(first)))]
        submit(pool, first)
        logger.info(
            "map-elites init: %d cells (%.0f%%)",
            len(archive.cells),
            100 * archive.coverage,
        )
        for it in range(iterations):
            elites = list(archive.cells.values())
            children = []
            for _ in range(batch):
                parent = rng.choice(elites).genome
                if len(elites) > 1 and rng.random() < 0.3:
                    parent = _crossover(parent, rng.choice(elites).genome, rng)
                children.append(_mutate(parent, rng, sigma))
            submit(pool, children)
            best = max(archive.cells.values(), key=lambda e: e.fitness)
            logger.info(
                "map-elites iter %d: %d cells (%.0f%%), best %.3f, QD %.1f",
                it,
                len(archive.cells),
                100 * archive.coverage,
                best.fitness,
                archive.qd_score,
            )
    me_id = _store(db_path, archive, xd, yd, x_name, y_name, iterations, evaluations)
    return MapResult(me_id, archive, evaluations)


def _store(
    db_path: Path,
    archive: Archive,
    xd: Descriptor,
    yd: Descriptor,
    x_name: str,
    y_name: str,
    iterations: int,
    evaluations: int,
) -> int:
    conn = results.connect(db_path)
    cur = conn.execute(
        "INSERT INTO map_elites_meta (created_at, x_name, y_name, x_label,"
        " y_label, x_max, y_max, x_bins, y_bins, iterations, evaluations)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            datetime.now(UTC).isoformat(),
            x_name,
            y_name,
            xd.label,
            yd.label,
            archive.x_max,
            archive.y_max,
            archive.x_bins,
            archive.y_bins,
            iterations,
            evaluations,
        ),
    )
    me_id = int(cur.lastrowid or 0)
    conn.executemany(
        "INSERT INTO map_elites VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                me_id,
                cx,
                cy,
                json.dumps(e.genome.to_json()),
                e.fitness,
                e.desc[0],
                e.desc[1],
                e.found_at,
            )
            for (cx, cy), e in sorted(archive.cells.items())
        ],
    )
    conn.commit()
    conn.close()
    return me_id
