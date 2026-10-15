"""Tests for the Outpost simulator: determinism, invariants, storage."""
from pathlib import Path

from app.outpost.rules.model import Params
from app.outpost.sim import results
from app.outpost.sim.runner import DEFAULT_ROSTER, RosterEntry, run_round
from app.outpost.sim.sweep import grid_points, run_sweep

SMALL = (
    RosterEntry("builder", 3),
    RosterEntry("raider", 3),
    RosterEntry("alliance", 4, group=4),
)


def test_same_seed_same_round() -> None:
    a = run_round(Params(), SMALL, seed=5)
    b = run_round(Params(), SMALL, seed=5)
    assert a.players == b.players
    assert a.metrics == b.metrics
    assert a.series == b.series


def test_param_change_changes_outcome() -> None:
    base = run_round(Params(), SMALL, seed=5)
    rich = run_round(Params(prod_mult_pct=200), SMALL, seed=5)
    assert (
        rich.metrics["median_power_builder"]
        > base.metrics["median_power_builder"]
    )


def test_default_round_holds_loss_cap() -> None:
    result = run_round(Params(), DEFAULT_ROSTER, seed=2)
    status = {name: ok for name, ok, _detail in result.invariants}
    assert status["p2_loss_cap"]
    assert status["no_negative_stock"]
    raids = result.metrics["raids_on_players"]
    assert raids > 0, "raiders must actually raid for the cap to be tested"


def test_loss_cap_tracks_bucket_param() -> None:
    result = run_round(Params(bucket_hours=1), DEFAULT_ROSTER, seed=2)
    worst = max(p["max_12h_loss_hours"] for p in result.players)
    assert worst <= 2.01


def test_sweep_stores_every_run(tmp_path: Path) -> None:
    points = list(grid_points({"vault_pct": [5, 20]}))
    db = tmp_path / "r.sqlite"
    sweep_id = run_sweep(db, "t", points, [1, 2], roster=SMALL, workers=1)
    conn = results.connect(db)
    runs = conn.execute(
        "SELECT COUNT(*) FROM runs WHERE sweep_id = ?", (sweep_id,)
    ).fetchone()[0]
    traced = conn.execute(
        "SELECT COUNT(*) FROM runs WHERE trace_path IS NOT NULL"
    ).fetchone()[0]
    players = conn.execute("SELECT COUNT(*) FROM player_results").fetchone()[0]
    assert runs == 4
    assert traced == 2  # first seed of each point
    assert players == 4 * 10
