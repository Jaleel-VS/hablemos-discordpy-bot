"""SQLite results store for sweeps, runs and evolution (contracts doc)."""
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from .runner import RunResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS sweeps (sweep_id INTEGER PRIMARY KEY, name TEXT,
  created_at TEXT, base_params TEXT);
CREATE TABLE IF NOT EXISTS runs (run_id INTEGER PRIMARY KEY, sweep_id INT,
  seed INT, params TEXT, varied TEXT, players INT, wall_s REAL,
  trace_path TEXT);
CREATE TABLE IF NOT EXISTS run_metrics (run_id INT, metric TEXT, value REAL,
  PRIMARY KEY (run_id, metric));
CREATE TABLE IF NOT EXISTS player_results (run_id INT, player_id INT,
  archetype TEXT, tz INT, joined_day INT, final_power REAL, final_eco REAL,
  army_value REAL, loot_gained REAL, loot_lost REAL, raid_income_share REAL,
  max_12h_loss_hours REAL, quit_day INT, alliance_id INT, bases INT,
  fakes_sent INT, dodges INT, explored INT, stance REAL,
  PRIMARY KEY (run_id, player_id));
CREATE TABLE IF NOT EXISTS series (run_id INT, player_id INT, t_h INT,
  power REAL, eco REAL, army_value REAL, stock_value REAL,
  PRIMARY KEY (run_id, player_id, t_h));
CREATE TABLE IF NOT EXISTS invariants (run_id INT, name TEXT, ok INT,
  detail TEXT, PRIMARY KEY (run_id, name));
CREATE TABLE IF NOT EXISTS evolution (evo_id INT, gen INT, idx INT,
  genome TEXT, fitness REAL, PRIMARY KEY (evo_id, gen, idx));
CREATE TABLE IF NOT EXISTS map_elites_meta (me_id INTEGER PRIMARY KEY,
  created_at TEXT, x_name TEXT, y_name TEXT, x_label TEXT, y_label TEXT,
  x_max REAL, y_max REAL, x_bins INT, y_bins INT, iterations INT,
  evaluations INT);
CREATE TABLE IF NOT EXISTS map_elites (me_id INT, cell_x INT, cell_y INT,
  genome TEXT, fitness REAL, desc_x REAL, desc_y REAL, found_at INT,
  PRIMARY KEY (me_id, cell_x, cell_y));
CREATE TABLE IF NOT EXISTS player_experience (run_id INT, player_id INT,
  frustration REAL, quit_risk REAL, unfair REAL, proud REAL, diary TEXT,
  PRIMARY KEY (run_id, player_id));
CREATE TABLE IF NOT EXISTS jev_decisions (run_id INT, player_id INT,
  t_h REAL, question TEXT, choice TEXT, confidence REAL);
"""

PLAYER_COLUMNS = (
    "player_id",
    "archetype",
    "tz",
    "joined_day",
    "final_power",
    "final_eco",
    "army_value",
    "loot_gained",
    "loot_lost",
    "raid_income_share",
    "max_12h_loss_hours",
    "quit_day",
    "alliance_id",
    "bases",
    "fakes_sent",
    "dodges",
    "explored",
    "stance",
)


def connect(path: Path) -> sqlite3.Connection:
    """Open (and create if needed) a results database."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn


def new_sweep(conn: sqlite3.Connection, name: str, base_params: dict) -> int:
    """Insert a sweep row and return its id."""
    cur = conn.execute(
        "INSERT INTO sweeps (name, created_at, base_params) VALUES (?, ?, ?)",
        (name, datetime.now(UTC).isoformat(), json.dumps(base_params)),
    )
    conn.commit()
    return int(cur.lastrowid or 0)


def save_run(
    conn: sqlite3.Connection,
    sweep_id: int,
    seed: int,
    params: dict,
    varied: dict,
    result: RunResult,
    *,
    trace_dir: Path | None = None,
    store_series: bool = True,
) -> int:
    """Persist one run; writes its trace JSON when present."""
    cur = conn.execute(
        "INSERT INTO runs (sweep_id, seed, params, varied, players, wall_s,"
        " trace_path) VALUES (?, ?, ?, ?, ?, ?, NULL)",
        (
            sweep_id,
            seed,
            json.dumps(params),
            json.dumps(varied),
            len(result.players),
            result.wall_s,
        ),
    )
    run_id = int(cur.lastrowid or 0)
    if result.trace is not None and trace_dir is not None:
        trace_dir.mkdir(parents=True, exist_ok=True)
        path = trace_dir / f"run_{run_id}.json"
        trace = dict(result.trace)
        trace["meta"] = {**trace["meta"], "run_id": run_id}
        path.write_text(json.dumps(trace))
        conn.execute(
            "UPDATE runs SET trace_path = ? WHERE run_id = ?",
            (str(path), run_id),
        )
    conn.executemany(
        "INSERT INTO run_metrics VALUES (?, ?, ?)",
        [(run_id, k, float(v)) for k, v in result.metrics.items()],
    )
    placeholders = ", ".join("?" for _ in range(len(PLAYER_COLUMNS) + 1))
    conn.executemany(
        f"INSERT INTO player_results VALUES ({placeholders})",
        [(run_id, *(p[c] for c in PLAYER_COLUMNS)) for p in result.players],
    )
    if store_series:
        conn.executemany(
            "INSERT OR REPLACE INTO series VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(run_id, *row[1:2], row[0], *row[2:]) for row in result.series],
        )
    conn.executemany(
        "INSERT INTO invariants VALUES (?, ?, ?, ?)",
        [(run_id, n, int(ok), d) for n, ok, d in result.invariants],
    )
    conn.executemany(
        "INSERT INTO player_experience VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (
                run_id,
                r["player_id"],
                r["frustration"],
                r["quit_risk"],
                r["unfair"],
                r["proud"],
                json.dumps(result.diaries.get(r["player_id"], {})),
            )
            for r in result.experience
        ],
    )
    conn.executemany(
        "INSERT INTO jev_decisions VALUES (?, ?, ?, ?, ?, ?)",
        [
            (run_id, d["player_id"], d["t_h"], d["question"], d["choice"],
             d["confidence"])
            for d in result.decisions
        ],
    )
    conn.commit()
    return run_id


def save_generation(
    conn: sqlite3.Connection,
    evo_id: int,
    gen: int,
    scored: list[tuple[dict, float]],
) -> None:
    """Persist one evolution generation."""
    conn.executemany(
        "INSERT OR REPLACE INTO evolution VALUES (?, ?, ?, ?, ?)",
        [
            (evo_id, gen, i, json.dumps(genome), fitness)
            for i, (genome, fitness) in enumerate(scored)
        ],
    )
    conn.commit()


def next_evo_id(conn: sqlite3.Connection) -> int:
    """Smallest unused evolution id."""
    row = conn.execute("SELECT MAX(evo_id) FROM evolution").fetchone()
    return int(row[0] or 0) + 1
