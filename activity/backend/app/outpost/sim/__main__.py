"""Outpost simulator CLI.

Run from ``activity/backend``::

    python -m app.outpost.sim run --seed 1 --trace
    python -m app.outpost.sim sweep --grid bucket_hours=2,4,6 \
        --grid vault_pct=5,10,20 --seeds 1,2,3
    python -m app.outpost.sim sweep --random monument_base=50000:300000 --n 20
    python -m app.outpost.sim evolve --generations 8 --population 12
    python -m app.outpost.sim map --x loot_share --y army_frac --iterations 8
    python -m app.outpost.sim report

Everything writes to ``--out`` (default ``sim_out/``): ``results.sqlite``,
``traces/`` and ``report.html``.
"""
import argparse
import logging
from pathlib import Path

from ..rules.model import Params
from . import dashboard, results
from .evolve import DOMINANT_FITNESS, evolve
from .experience import judge_run
from .jev import JevController, decision_metrics
from .mapelites import DESCRIPTORS, run_map_elites
from .runner import DEFAULT_ROSTER, RosterEntry, run_round
from .sweep import grid_points, random_points, run_sweep


def _int_list(text: str) -> list[int]:
    return [int(v) for v in text.split(",") if v]


def _grid(items: list[str]) -> dict[str, list[int]]:
    out = {}
    for item in items:
        name, _, values = item.partition("=")
        out[name] = _int_list(values)
    return out


def _ranges(items: list[str]) -> dict[str, list[int]]:
    out = {}
    for item in items:
        name, _, span = item.partition("=")
        lo, _, hi = span.partition(":")
        out[name] = [int(lo), int(hi)]
    return out


def _base(items: list[str]) -> Params:
    changes = {}
    for item in items:
        name, _, value = item.partition("=")
        changes[name] = int(value)
    return Params().with_changes(**changes)


def main(argv: list[str] | None = None) -> None:
    """Parse arguments and dispatch a subcommand."""
    parser = argparse.ArgumentParser(prog="python -m app.outpost.sim")
    parser.add_argument("--out", type=Path, default=Path("sim_out"))
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="PARAM=VALUE",
        help="override a base parameter (repeatable)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="simulate one round")
    run_p.add_argument("--seed", type=int, default=1)
    run_p.add_argument("--trace", action="store_true")
    run_p.add_argument(
        "--judge",
        action="store_true",
        help="score each player's experience with Jev (needs TYPESAFE_API_KEY)",
    )
    run_p.add_argument(
        "--jev",
        type=int,
        default=0,
        metavar="N",
        help="add N players whose key calls are made by Jev",
    )

    sweep_p = sub.add_parser("sweep", help="run a parameter sweep")
    sweep_p.add_argument("--name", default="sweep")
    sweep_p.add_argument("--grid", action="append", default=[])
    sweep_p.add_argument("--random", action="append", default=[])
    sweep_p.add_argument("--n", type=int, default=10)
    sweep_p.add_argument("--seeds", type=_int_list, default=[1, 2, 3])
    sweep_p.add_argument("--workers", type=int, default=0)
    sweep_p.add_argument("--judge", action="store_true")

    evo_p = sub.add_parser("evolve", help="search for dominant strategies")
    evo_p.add_argument("--generations", type=int, default=8)
    evo_p.add_argument("--population", type=int, default=12)
    evo_p.add_argument("--cohort", type=int, default=4)
    evo_p.add_argument("--seeds", type=_int_list, default=[1, 2])
    evo_p.add_argument("--workers", type=int, default=0)

    map_p = sub.add_parser("map", help="MAP-Elites: best strategy per style")
    map_p.add_argument("--x", default="loot_share", choices=sorted(DESCRIPTORS))
    map_p.add_argument("--y", default="army_frac", choices=sorted(DESCRIPTORS))
    map_p.add_argument("--bins", type=int, default=8)
    map_p.add_argument("--initial", type=int, default=24)
    map_p.add_argument("--iterations", type=int, default=8)
    map_p.add_argument("--batch", type=int, default=16)
    map_p.add_argument("--seeds", type=_int_list, default=[1, 2])
    map_p.add_argument("--workers", type=int, default=0)

    sub.add_parser("report", help="build report.html from results")

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    out: Path = args.out
    db = out / "results.sqlite"
    base = _base(args.set)

    if args.cmd == "run":
        roster = DEFAULT_ROSTER
        controllers = {}
        jev = None
        if args.jev:
            jev = JevController.from_env(out / "jev_cache.sqlite")
            roster = (*DEFAULT_ROSTER, RosterEntry("jev", args.jev))
            controllers = {"jev": jev}
        result = run_round(
            base,
            roster,
            seed=args.seed,
            trace=args.trace,
            controllers=controllers,
        )
        if jev is not None:
            result.decisions = jev.log
            result.metrics.update(decision_metrics(jev.log))
            result.metrics["jev_api_calls"] = float(jev.calls)
            result.metrics["jev_cache_hits"] = float(jev.cache_hits)
        if args.judge:
            judge_run(result)
        conn = results.connect(db)
        sweep_id = results.new_sweep(conn, f"run seed {args.seed}", base.to_json())
        results.save_run(
            conn, sweep_id, args.seed, base.to_json(), {}, result,
            trace_dir=out / "traces",
        )
        conn.close()
        print(f"round simulated in {result.wall_s:.1f}s (sweep {sweep_id})")
        for name, value in sorted(result.metrics.items()):
            print(f"  {name:28} {value:12.2f}")
        for name, ok, detail in result.invariants:
            print(f"  {'PASS' if ok else 'FAIL'} {name}: {detail}")
    elif args.cmd == "sweep":
        if args.grid:
            points = list(grid_points(_grid(args.grid)))
        elif args.random:
            points = list(random_points(_ranges(args.random), args.n, 0))
        else:
            parser.error("sweep needs --grid or --random")
        sweep_id = run_sweep(
            db,
            args.name,
            points,
            args.seeds,
            base=base,
            workers=args.workers,
            judge=args.judge,
        )
        print(f"sweep {sweep_id}: {len(points) * len(args.seeds)} runs")
    elif args.cmd == "evolve":
        res = evolve(
            db,
            generations=args.generations,
            population=args.population,
            cohort=args.cohort,
            seeds=tuple(args.seeds),
            params=base,
            workers=args.workers,
        )
        verdict = "DOMINANT — inspect the rules" if res.dominant else "none"
        print(f"evolution {res.evo_id}: best fitness {res.best_fitness:.3f}")
        print(f"  dominant strategy: {verdict}")
        print(f"  best genome: {res.best.to_json()}")
    elif args.cmd == "map":
        mres = run_map_elites(
            db,
            x_name=args.x,
            y_name=args.y,
            bins=args.bins,
            initial=args.initial,
            iterations=args.iterations,
            batch=args.batch,
            seeds=tuple(args.seeds),
            params=base,
            workers=args.workers,
        )
        arch = mres.archive
        print(
            f"map {mres.me_id}: {len(arch.cells)} cells filled"
            f" ({100 * arch.coverage:.0f}%), QD-score {arch.qd_score:.1f},"
            f" {mres.evaluations} evaluations"
        )
        broken = [
            (k, e) for k, e in arch.cells.items() if e.fitness > DOMINANT_FITNESS
        ]
        for (cx, cy), e in sorted(broken, key=lambda ke: -ke[1].fitness)[:5]:
            print(
                f"  DOMINANT cell ({cx},{cy}) fitness {e.fitness:.2f}"
                f" {args.x}={e.desc[0]:.2f} {args.y}={e.desc[1]:.2f}"
            )
    dashboard.build_dashboard(db, out / "report.html")
    print(f"report: {out / 'report.html'}")


if __name__ == "__main__":
    main()
