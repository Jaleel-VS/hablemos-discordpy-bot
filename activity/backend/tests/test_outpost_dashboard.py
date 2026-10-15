"""Tests for app.outpost.sim.dashboard.build_dashboard."""

from __future__ import annotations

import json
import sqlite3
import tempfile
from html.parser import HTMLParser
from pathlib import Path

import pytest
from app.outpost.sim.dashboard import build_dashboard

# ──────────────────────────────────────────────────────────────────────────────
# Schema helpers
# ──────────────────────────────────────────────────────────────────────────────

_DDL = """
CREATE TABLE sweeps (
    sweep_id INTEGER PRIMARY KEY,
    name TEXT,
    created_at TEXT,
    base_params TEXT
);
CREATE TABLE runs (
    run_id INTEGER PRIMARY KEY,
    sweep_id INT,
    seed INT,
    params TEXT,
    varied TEXT,
    players INT,
    wall_s REAL,
    trace_path TEXT
);
CREATE TABLE run_metrics (
    run_id INT,
    metric TEXT,
    value REAL,
    PRIMARY KEY (run_id, metric)
);
CREATE TABLE player_results (
    run_id INT,
    player_id INT,
    archetype TEXT,
    tz INT,
    joined_day INT,
    final_power REAL,
    final_eco REAL,
    army_value REAL,
    loot_gained REAL,
    loot_lost REAL,
    raid_income_share REAL,
    max_12h_loss_hours REAL,
    quit_day INT,
    alliance_id INT,
    PRIMARY KEY (run_id, player_id)
);
CREATE TABLE series (
    run_id INT,
    player_id INT,
    t_h INT,
    power REAL,
    eco REAL,
    army_value REAL,
    stock_value REAL,
    PRIMARY KEY (run_id, player_id, t_h)
);
CREATE TABLE invariants (
    run_id INT,
    name TEXT,
    ok INT,
    detail TEXT,
    PRIMARY KEY (run_id, name)
);
CREATE TABLE evolution (
    evo_id INT,
    gen INT,
    idx INT,
    genome TEXT,
    fitness REAL,
    PRIMARY KEY (evo_id, gen, idx)
);
"""

_ME_DDL = """
CREATE TABLE IF NOT EXISTS map_elites_meta (
    me_id INTEGER PRIMARY KEY,
    created_at TEXT,
    x_name TEXT, y_name TEXT,
    x_label TEXT, y_label TEXT,
    x_max REAL, y_max REAL,
    x_bins INT, y_bins INT,
    iterations INT, evaluations INT
);
CREATE TABLE IF NOT EXISTS map_elites (
    me_id INT, cell_x INT, cell_y INT,
    genome TEXT,
    fitness REAL,
    desc_x REAL, desc_y REAL,
    found_at INT,
    PRIMARY KEY (me_id, cell_x, cell_y)
);
"""

# Cell layout for 4×4 grid (6 filled cells, one dominant with fitness 1.5):
_ME_CELLS = [
    # (cell_x, cell_y, fitness, desc_x, desc_y, found_at, genome)
    (0, 0, 0.8,  0.1, 0.1, 10,  {"hall_cap": 4, "barracks_cap": 2}),
    (1, 0, 0.95, 0.3, 0.1, 20,  {"hall_cap": 5, "barracks_cap": 3}),
    (2, 1, 1.1,  0.5, 0.3, 30,  {"hall_cap": 6, "barracks_cap": 3}),
    (3, 2, 1.2,  0.7, 0.5, 40,  {"hall_cap": 7, "barracks_cap": 4}),
    (1, 3, 1.3,  0.3, 0.9, 50,  {"hall_cap": 5, "barracks_cap": 5}),
    (3, 3, 1.5,  0.9, 0.9, 60,  {"hall_cap": 8, "barracks_cap": 6}),  # dominant
]


def _build_me_db(tmp_dir: Path) -> Path:
    """Create a minimal DB with map_elites tables populated (me_id=1, 4×4 bins)."""
    db_path = tmp_dir / "me_results.sqlite"
    conn = sqlite3.connect(db_path)
    conn.executescript(_DDL + _ME_DDL)
    # minimal sweep so build_dashboard doesn't warn
    conn.execute(
        "INSERT INTO sweeps VALUES (1, 'me-sweep', '2026-01-01T00:00:00', ?)",
        (json.dumps({}),),
    )
    conn.execute(
        "INSERT INTO map_elites_meta VALUES (1, '2026-01-01T00:00:00',"
        " 'aggression', 'economy',"
        " 'Aggression', 'Economy',"
        " 1.0, 1.0, 4, 4, 200, 2000)"
    )
    for cx, cy, fitness, dx, dy, found_at, genome in _ME_CELLS:
        conn.execute(
            "INSERT INTO map_elites VALUES (1, ?, ?, ?, ?, ?, ?, ?)",
            (cx, cy, json.dumps(genome), fitness, dx, dy, found_at),
        )
    conn.commit()
    conn.close()
    return db_path


def _build_db_without_me_tables(tmp_dir: Path) -> Path:
    """Create a DB with only the standard tables (no map_elites tables)."""
    db_path = tmp_dir / "no_me_results.sqlite"
    conn = sqlite3.connect(db_path)
    conn.executescript(_DDL)
    conn.execute(
        "INSERT INTO sweeps VALUES (1, 'plain-sweep', '2026-01-01T00:00:00', ?)",
        (json.dumps({}),),
    )
    conn.commit()
    conn.close()
    return db_path


def _build_db(tmp_dir: Path) -> tuple[Path, Path]:
    """Create a synthetic sweep database and a trace file.

    Returns (db_path, trace_path).
    """
    db_path = tmp_dir / "results.sqlite"
    trace_path = tmp_dir / "trace_run1.json"

    conn = sqlite3.connect(db_path)
    conn.executescript(_DDL)

    # sweep
    conn.execute(
        "INSERT INTO sweeps VALUES (1, 'test-sweep', '2026-01-01T00:00:00', ?)",
        (json.dumps({"speed": 100, "players": 4}),),
    )

    # 2 varied params × 2 values × 2 seeds = 8 runs
    run_id = 0
    for hall_cap in (5, 10):
        for barracks_cap in (3, 6):
            for seed in (42, 99):
                run_id += 1
                varied = json.dumps(
                    {"hall_cap": hall_cap, "barracks_cap": barracks_cap}
                )
                params = json.dumps(
                    {"hall_cap": hall_cap, "barracks_cap": barracks_cap, "speed": 100}
                )
                tp = str(trace_path) if run_id == 1 else None
                conn.execute(
                    "INSERT INTO runs VALUES (?, 1, ?, ?, ?, 4, ?, ?)",
                    (run_id, seed, params, varied, 1.23, tp),
                )
                conn.execute(
                    "INSERT INTO run_metrics VALUES (?, 'quit_rate', ?)",
                    (run_id, 0.1 + run_id * 0.02),
                )
                conn.execute(
                    "INSERT INTO run_metrics VALUES (?, 'gini_power', ?)",
                    (run_id, 0.3 + run_id * 0.01),
                )
                # player results: 4 players, 2 archetypes
                for pid in range(1, 5):
                    arch = "raider" if pid <= 2 else "builder"
                    conn.execute(
                        "INSERT INTO player_results "
                        "(run_id, player_id, archetype, tz, joined_day, "
                        "final_power, final_eco, army_value, loot_gained, "
                        "loot_lost, raid_income_share, max_12h_loss_hours, "
                        "quit_day, alliance_id) "
                        "VALUES (?, ?, ?, 0, 0, ?, ?, ?, ?, ?, ?, ?, NULL, 1)",
                        (
                            run_id,
                            pid,
                            arch,
                            1000.0 + pid * 100 + run_id * 10,
                            500.0 + pid * 50,
                            200.0 + pid * 20,
                            300.0 + pid * 30,
                            100.0 + pid * 10,
                            0.25,
                            2.0,
                        ),
                    )
                # series: power every 24 h for 3 days
                for pid in range(1, 5):
                    for t_h in (0, 24, 48, 72):
                        conn.execute(
                            "INSERT INTO series VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (
                                run_id,
                                pid,
                                t_h,
                                900.0 + t_h * 5 + pid * 10,
                                400.0 + t_h * 2,
                                180.0 + t_h,
                                220.0 + t_h,
                            ),
                        )
                # invariants: pass for first 7 runs, one fail on run 8
                ok = 1 if run_id < 8 else 0
                detail = None if ok else "max/min ratio 3.1 > 2.5"
                conn.execute(
                    "INSERT OR IGNORE INTO invariants VALUES (?, ?, ?, ?)",
                    (run_id, "no_archetype_dominates", ok, detail),
                )
                conn.execute(
                    "INSERT OR IGNORE INTO invariants VALUES (?, ?, ?, ?)",
                    (run_id, "p2_loss_cap", 1, None),
                )

    # evolution rows: 3 generations × 4 individuals
    for gen in range(3):
        for idx in range(4):
            conn.execute(
                "INSERT INTO evolution VALUES (1, ?, ?, ?, ?)",
                (
                    gen,
                    idx,
                    json.dumps({"hall_cap": 5 + gen, "barracks_cap": 3 + idx}),
                    float(gen * 10 + idx * 2),
                ),
            )

    conn.commit()
    conn.close()

    # trace file for run 1
    trace = {
        "meta": {
            "run_id": 1,
            "seed": 42,
            "radius": 10,
            "days": 3,
            "params": {},
            "players": [
                {"id": 1, "archetype": "raider", "tz": 0, "alliance": 1, "color_key": 0},
                {"id": 2, "archetype": "builder", "tz": 0, "alliance": 1, "color_key": 1},
            ],
        },
        "bases": [
            {"id": 10, "x": -3, "y": 2, "kind": "player", "tier": 1, "owner": 1,
             "from_h": 0, "to_h": None},
            {"id": 11, "x": 3, "y": -2, "kind": "player", "tier": 1, "owner": 2,
             "from_h": 0, "to_h": None},
            {"id": 20, "x": 0, "y": 0, "kind": "camp", "tier": 1, "owner": 0,
             "from_h": 0, "to_h": None},
        ],
        "marches": [
            {"id": 5, "owner": 1, "mission": "raid", "from": [-3, 2], "to": [0, 0],
             "depart_h": 1.0, "arrive_h": 1.5, "return_h": 2.0, "outcome": "won"},
        ],
        "battles": [
            {"t_h": 1.5, "x": 0, "y": 0, "attacker": 1, "defender": 0,
             "attacker_won": True, "loot": 500.0, "kind": "raid"},
        ],
        "series": {
            "1": [[0, 1000.0, 400.0, 200.0], [24, 1100.0, 420.0, 210.0]],
            "2": [[0, 950.0, 380.0, 180.0], [24, 1050.0, 400.0, 190.0]],
        },
    }
    trace_path.write_text(json.dumps(trace), encoding="utf-8")

    return db_path, trace_path


class _HTMLChecker(HTMLParser):
    """Collect external http/https references and tag ids."""

    def __init__(self) -> None:
        super().__init__()
        self.external_refs: list[str] = []
        self.ids: set[str] = set()
        self.errors: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        attr_dict = dict(attrs)
        elem_id = attr_dict.get("id")
        if elem_id:
            self.ids.add(elem_id)
        src = attr_dict.get("src") or ""
        href = attr_dict.get("href") or ""
        for ref in (src, href):
            if (ref.startswith("http://") or ref.startswith("https://")) and tag in ("script", "link"):
                self.external_refs.append(ref)

    def handle_error(self, message: str) -> None:
        self.errors.append(message)


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def tmp_dir(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture()
def db_and_trace(tmp_dir: Path) -> tuple[Path, Path]:
    return _build_db(tmp_dir)


# ──────────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestBuildDashboard:
    def test_html_file_created(
        self, db_and_trace: tuple[Path, Path], tmp_dir: Path
    ) -> None:
        db_path, _ = db_and_trace
        out = tmp_dir / "report.html"
        result = build_dashboard(db_path, out)
        assert result == out.resolve()
        assert out.exists()
        assert out.stat().st_size > 1000

    def test_panel_ids_present(
        self, db_and_trace: tuple[Path, Path], tmp_dir: Path
    ) -> None:
        db_path, _ = db_and_trace
        out = tmp_dir / "report.html"
        build_dashboard(db_path, out)
        html = out.read_text(encoding="utf-8")
        for panel_id in (
            "sweep-panel",
            "arch-panel",
            "inv-panel",
            "evo-panel",
            "map-panel",
            "panel-strategy-map",
        ):
            assert panel_id in html, f"Missing panel id: {panel_id}"

    def test_embedded_json_parseable(
        self, db_and_trace: tuple[Path, Path], tmp_dir: Path
    ) -> None:
        db_path, _ = db_and_trace
        out = tmp_dir / "report.html"
        build_dashboard(db_path, out)
        html = out.read_text(encoding="utf-8")
        start = html.index('id="app-data">') + len('id="app-data">')
        end = html.index("</script>", start)
        payload = json.loads(html[start:end])
        assert payload["run_count"] == 8

    def test_no_external_script_or_link_refs(
        self, db_and_trace: tuple[Path, Path], tmp_dir: Path
    ) -> None:
        db_path, _ = db_and_trace
        out = tmp_dir / "report.html"
        build_dashboard(db_path, out)
        html = out.read_text(encoding="utf-8")
        checker = _HTMLChecker()
        checker.feed(html)
        assert not checker.external_refs, (
            f"External http(s) script/link refs found: {checker.external_refs}"
        )

    def test_html_parses_without_error(
        self, db_and_trace: tuple[Path, Path], tmp_dir: Path
    ) -> None:
        db_path, _ = db_and_trace
        out = tmp_dir / "report.html"
        build_dashboard(db_path, out)
        html = out.read_text(encoding="utf-8")
        checker = _HTMLChecker()
        checker.feed(html)
        assert not checker.errors, f"HTML parse errors: {checker.errors}"

    def test_sweep_filter(
        self, db_and_trace: tuple[Path, Path], tmp_dir: Path
    ) -> None:
        db_path, _ = db_and_trace
        out = tmp_dir / "report_s1.html"
        build_dashboard(db_path, out, sweep_id=1)
        html = out.read_text(encoding="utf-8")
        start = html.index('id="app-data">') + len('id="app-data">')
        end = html.index("</script>", start)
        payload = json.loads(html[start:end])
        # all 8 runs belong to sweep 1
        assert payload["run_count"] == 8

    def test_sweep_filter_missing_sweep(
        self, db_and_trace: tuple[Path, Path], tmp_dir: Path
    ) -> None:
        db_path, _ = db_and_trace
        out = tmp_dir / "report_s99.html"
        build_dashboard(db_path, out, sweep_id=99)
        html = out.read_text(encoding="utf-8")
        start = html.index('id="app-data">') + len('id="app-data">')
        end = html.index("</script>", start)
        payload = json.loads(html[start:end])
        assert payload["run_count"] == 0

    def test_heatmap_generated_for_2_varied_params(
        self, db_and_trace: tuple[Path, Path], tmp_dir: Path
    ) -> None:
        db_path, _ = db_and_trace
        out = tmp_dir / "report.html"
        build_dashboard(db_path, out)
        html = out.read_text(encoding="utf-8")
        start = html.index('id="app-data">') + len('id="app-data">')
        end = html.index("</script>", start)
        payload = json.loads(html[start:end])
        hm = payload["overview"]["heatmap"]
        assert hm is not None
        assert hm["param0"] in ("barracks_cap", "hall_cap")
        assert hm["param1"] in ("barracks_cap", "hall_cap")
        assert len(hm["vals0"]) == 2
        assert len(hm["vals1"]) == 2

    def test_archetype_power_stats_present(
        self, db_and_trace: tuple[Path, Path], tmp_dir: Path
    ) -> None:
        db_path, _ = db_and_trace
        out = tmp_dir / "report.html"
        build_dashboard(db_path, out)
        html = out.read_text(encoding="utf-8")
        start = html.index('id="app-data">') + len('id="app-data">')
        end = html.index("</script>", start)
        payload = json.loads(html[start:end])
        ps = payload["archetype"]["power_stats"]
        assert "raider" in ps
        assert "builder" in ps
        assert ps["raider"]["median"] > 0

    def test_invariant_summary_present(
        self, db_and_trace: tuple[Path, Path], tmp_dir: Path
    ) -> None:
        db_path, _ = db_and_trace
        out = tmp_dir / "report.html"
        build_dashboard(db_path, out)
        html = out.read_text(encoding="utf-8")
        start = html.index('id="app-data">') + len('id="app-data">')
        end = html.index("</script>", start)
        payload = json.loads(html[start:end])
        inv = payload["invariants"]
        assert "no_archetype_dominates" in inv["summary"]
        # run 8 has a failing invariant
        assert any(
            r["name"] == "no_archetype_dominates" for r in inv["failing"]
        )

    def test_evolution_data_present(
        self, db_and_trace: tuple[Path, Path], tmp_dir: Path
    ) -> None:
        db_path, _ = db_and_trace
        out = tmp_dir / "report.html"
        build_dashboard(db_path, out)
        html = out.read_text(encoding="utf-8")
        start = html.index('id="app-data">') + len('id="app-data">')
        end = html.index("</script>", start)
        payload = json.loads(html[start:end])
        evo = payload["evolution"]
        assert evo["gens"] == [0, 1, 2]
        assert len(evo["best_fitness"]) == 3
        # best fitness per gen: gen0 max=6, gen1 max=16, gen2 max=26
        assert evo["best_fitness"][2] > evo["best_fitness"][0]

    def test_trace_embedded(
        self, db_and_trace: tuple[Path, Path], tmp_dir: Path
    ) -> None:
        db_path, _ = db_and_trace
        out = tmp_dir / "report.html"
        build_dashboard(db_path, out)
        html = out.read_text(encoding="utf-8")
        start = html.index('id="app-data">') + len('id="app-data">')
        end = html.index("</script>", start)
        payload = json.loads(html[start:end])
        assert len(payload["traces"]) == 1
        assert payload["traces"][0]["meta"]["run_id"] == 1


# ──────────────────────────────────────────────────────────────────────────────
# Strategy map tab tests
# ──────────────────────────────────────────────────────────────────────────────


class TestStrategyMapTab:
    """Tests for the MAP-Elites Strategy map tab."""

    def _get_payload(self, html: str) -> dict:
        start = html.index('id="app-data">') + len('id="app-data">')
        end = html.index("</script>", start)
        return json.loads(html[start:end])

    def test_panel_present(self, tmp_path: Path) -> None:
        """panel-strategy-map id is in HTML regardless of ME data."""
        db_path = _build_me_db(tmp_path)
        out = tmp_path / "me_report.html"
        build_dashboard(db_path, out)
        html = out.read_text(encoding="utf-8")
        assert "panel-strategy-map" in html

    def test_six_cells_embedded(self, tmp_path: Path) -> None:
        """Payload contains 6 cells for me_id=1 when table is populated."""
        db_path = _build_me_db(tmp_path)
        out = tmp_path / "me_report.html"
        build_dashboard(db_path, out)
        html = out.read_text(encoding="utf-8")
        payload = self._get_payload(html)
        me = payload["map_elites"]
        assert me is not None, "map_elites key should be present"
        assert me["me_id"] == 1
        assert len(me["cells"]) == 6

    def test_dominant_cell_present(self, tmp_path: Path) -> None:
        """Cell with fitness 1.5 is included and best_fitness reflects it."""
        db_path = _build_me_db(tmp_path)
        out = tmp_path / "me_report.html"
        build_dashboard(db_path, out)
        html = out.read_text(encoding="utf-8")
        payload = self._get_payload(html)
        me = payload["map_elites"]
        assert me["best_fitness"] == pytest.approx(1.5)
        assert me["best_cell_x"] == 3
        assert me["best_cell_y"] == 3

    def test_stats_computed(self, tmp_path: Path) -> None:
        """Coverage, QD-score, iteration/evaluation counts are correct."""
        db_path = _build_me_db(tmp_path)
        out = tmp_path / "me_report.html"
        build_dashboard(db_path, out)
        html = out.read_text(encoding="utf-8")
        payload = self._get_payload(html)
        me = payload["map_elites"]
        # 6 filled / 16 total = 0.375
        assert me["coverage"] == pytest.approx(6 / 16)
        expected_qd = sum(c[2] for c in _ME_CELLS)
        assert me["qd_score"] == pytest.approx(expected_qd)
        assert me["iterations"] == 200
        assert me["evaluations"] == 2000

    def test_empty_state_without_me_tables(self, tmp_path: Path) -> None:
        """When map_elites tables are absent the dashboard still builds
        and shows the empty-state hint text."""
        db_path = _build_db_without_me_tables(tmp_path)
        out = tmp_path / "no_me_report.html"
        build_dashboard(db_path, out)  # must not raise
        html = out.read_text(encoding="utf-8")
        assert "panel-strategy-map" in html
        payload = self._get_payload(html)
        assert payload["map_elites"] is None
        # empty-state text is rendered statically in the HTML
        assert "python -m app.outpost.sim map" in html


# ──────────────────────────────────────────────────────────────────────────────
# Live HTML generation smoke test
# ──────────────────────────────────────────────────────────────────────────────


def test_generate_html_to_tmp() -> None:
    """Build a real HTML file under /tmp and assert it is loadable."""
    with tempfile.TemporaryDirectory(prefix="outpost_dash_") as td:
        tmp = Path(td)
        db_path, _ = _build_db(tmp)
        out = Path("/tmp/outpost_report.html")
        result = build_dashboard(db_path, out)
        assert result.exists()
        html = result.read_text(encoding="utf-8")
        checker = _HTMLChecker()
        checker.feed(html)
        assert not checker.errors
        print(f"Dashboard written to: {result}")
