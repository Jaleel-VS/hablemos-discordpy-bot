"""Parameter sweeps: run many rounds across param permutations in parallel.

Grid sweeps take ``{"param": [v1, v2, ...]}``; random sweeps draw ``n``
points uniformly from ``{"param": [lo, hi]}`` ranges (integers). Every point
runs over the same seeds so configurations are compared on identical maps
(common random numbers).
"""
import itertools
import logging
import random
from collections.abc import Iterator
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from ..rules.model import Params
from . import results
from .experience import judge_run
from .runner import DEFAULT_ROSTER, RosterEntry, RunResult, run_round

logger = logging.getLogger(__name__)

# Each sweep worker judges with a few threads; workers run in parallel too.
SWEEP_JUDGE_CONCURRENCY = 4


@dataclass(frozen=True, slots=True)
class Job:
    """One round to run."""

    varied: tuple[tuple[str, int], ...]
    seed: int
    trace: bool
    judge: bool = False


def grid_points(grid: dict[str, list[int]]) -> Iterator[dict[str, int]]:
    """Cartesian product of a parameter grid."""
    names = sorted(grid)
    for combo in itertools.product(*(grid[n] for n in names)):
        yield dict(zip(names, combo, strict=True))


def random_points(
    ranges: dict[str, list[int]], n: int, seed: int
) -> Iterator[dict[str, int]]:
    """``n`` uniform integer samples from ``{param: [lo, hi]}``."""
    rng = random.Random(seed)
    names = sorted(ranges)
    for _ in range(n):
        yield {k: rng.randint(ranges[k][0], ranges[k][1]) for k in names}


def _run_job(
    args: tuple[Params, tuple[RosterEntry, ...], Job, float],
) -> tuple[Job, RunResult]:
    base, roster, job, quit_hours = args
    params = base.with_changes(**dict(job.varied))
    result = run_round(
        params, roster, job.seed, trace=job.trace, quit_hours=quit_hours
    )
    if job.judge:
        judge_run(result, concurrency=SWEEP_JUDGE_CONCURRENCY)
    return job, result


def run_sweep(
    db_path: Path,
    name: str,
    points: list[dict[str, int]],
    seeds: list[int],
    *,
    base: Params | None = None,
    roster: tuple[RosterEntry, ...] = DEFAULT_ROSTER,
    workers: int = 0,
    trace_first_seed: bool = True,
    quit_hours: float = 24.0,
    judge: bool = False,
) -> int:
    """Run every point × seed, store results, return the sweep id."""
    base = base or Params()
    for point in points:
        base.with_changes(**point)  # fail fast on unknown param names
    conn = results.connect(db_path)
    sweep_id = results.new_sweep(conn, name, base.to_json())
    jobs = [
        Job(
            tuple(sorted(point.items())),
            seed,
            trace_first_seed and i == 0,
            judge,
        )
        for point in points
        for i, seed in enumerate(seeds)
    ]
    trace_dir = db_path.parent / "traces"
    args = [(base, roster, job, quit_hours) for job in jobs]
    logger.info("sweep %s: %d runs", name, len(jobs))
    if workers == 1:
        outputs = map(_run_job, args)
        _store_all(conn, sweep_id, base, outputs, trace_dir, len(jobs))
    else:
        with ProcessPoolExecutor(max_workers=workers or None) as pool:
            outputs = pool.map(_run_job, args, chunksize=1)
            _store_all(conn, sweep_id, base, outputs, trace_dir, len(jobs))
    conn.close()
    return sweep_id


def _store_all(
    conn,
    sweep_id: int,
    base: Params,
    outputs: Iterator[tuple[Job, RunResult]],
    trace_dir: Path,
    total: int,
) -> None:
    for done, (job, result) in enumerate(outputs, 1):
        varied = dict(job.varied)
        results.save_run(
            conn,
            sweep_id,
            job.seed,
            base.with_changes(**varied).to_json(),
            varied,
            result,
            trace_dir=trace_dir,
        )
        if done % 10 == 0 or done == total:
            logger.info("sweep %d: %d/%d runs stored", sweep_id, done, total)
