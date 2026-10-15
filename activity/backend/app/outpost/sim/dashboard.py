"""Build a self-contained HTML dashboard from an Outpost results DB.

CLI::

    python -m app.outpost.sim.dashboard --db results.sqlite \\
        --out report.html [--sweep N]
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data layer
# ---------------------------------------------------------------------------


def _fetch_sweeps(
    conn: sqlite3.Connection, sweep_id: int | None
) -> list[dict[str, Any]]:
    if sweep_id is not None:
        rows = conn.execute(
            "SELECT sweep_id, name, created_at, base_params "
            "FROM sweeps WHERE sweep_id = ?",
            (sweep_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT sweep_id, name, created_at, base_params FROM sweeps"
        ).fetchall()
    return [
        {
            "sweep_id": r[0],
            "name": r[1],
            "created_at": r[2],
            "base_params": r[3],
        }
        for r in rows
    ]


def _fetch_runs(
    conn: sqlite3.Connection, sweep_ids: list[int]
) -> list[dict[str, Any]]:
    placeholders = ",".join("?" * len(sweep_ids))
    rows = conn.execute(
        f"SELECT run_id, sweep_id, seed, params, varied, "
        f"players, wall_s, trace_path "
        f"FROM runs WHERE sweep_id IN ({placeholders})",
        sweep_ids,
    ).fetchall()
    return [
        {
            "run_id": r[0],
            "sweep_id": r[1],
            "seed": r[2],
            "params": r[3],
            "varied": r[4],
            "players": r[5],
            "wall_s": r[6],
            "trace_path": r[7],
        }
        for r in rows
    ]


def _fetch_metrics(
    conn: sqlite3.Connection, run_ids: list[int]
) -> dict[int, dict[str, float]]:
    if not run_ids:
        return {}
    placeholders = ",".join("?" * len(run_ids))
    rows = conn.execute(
        f"SELECT run_id, metric, value FROM run_metrics "
        f"WHERE run_id IN ({placeholders})",
        run_ids,
    ).fetchall()
    out: dict[int, dict[str, float]] = {}
    for run_id, metric, value in rows:
        out.setdefault(run_id, {})[metric] = value
    return out


def _fetch_player_results(
    conn: sqlite3.Connection, run_ids: list[int]
) -> list[dict[str, Any]]:
    if not run_ids:
        return []
    placeholders = ",".join("?" * len(run_ids))
    rows = conn.execute(
        f"SELECT run_id, player_id, archetype, tz, joined_day, "
        f"final_power, final_eco, army_value, loot_gained, loot_lost, "
        f"raid_income_share, max_12h_loss_hours, quit_day, alliance_id "
        f"FROM player_results WHERE run_id IN ({placeholders})",
        run_ids,
    ).fetchall()
    cols = [
        "run_id",
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
    ]
    return [dict(zip(cols, r, strict=True)) for r in rows]


def _fetch_series(
    conn: sqlite3.Connection, run_ids: list[int]
) -> list[dict[str, Any]]:
    if not run_ids:
        return []
    placeholders = ",".join("?" * len(run_ids))
    rows = conn.execute(
        f"SELECT run_id, player_id, t_h, power, eco, army_value, stock_value "
        f"FROM series WHERE run_id IN ({placeholders})",
        run_ids,
    ).fetchall()
    cols = [
        "run_id",
        "player_id",
        "t_h",
        "power",
        "eco",
        "army_value",
        "stock_value",
    ]
    return [dict(zip(cols, r, strict=True)) for r in rows]


def _fetch_invariants(
    conn: sqlite3.Connection, run_ids: list[int]
) -> list[dict[str, Any]]:
    if not run_ids:
        return []
    placeholders = ",".join("?" * len(run_ids))
    rows = conn.execute(
        f"SELECT run_id, name, ok, detail "
        f"FROM invariants WHERE run_id IN ({placeholders})",
        run_ids,
    ).fetchall()
    return [
        {"run_id": r[0], "name": r[1], "ok": r[2], "detail": r[3]}
        for r in rows
    ]


def _fetch_evolution(
    conn: sqlite3.Connection,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT evo_id, gen, idx, genome, fitness FROM evolution"
    ).fetchall()
    return [
        {
            "evo_id": r[0],
            "gen": r[1],
            "idx": r[2],
            "genome": r[3],
            "fitness": r[4],
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Analytics helpers
# ---------------------------------------------------------------------------


def _pct(values: list[float], p: float) -> float:
    """Return the p-th percentile (0–100) of values, linear interpolation."""
    if not values:
        return 0.0
    sv = sorted(values)
    n = len(sv)
    idx = p / 100 * (n - 1)
    lo = math.floor(idx)
    hi = min(lo + 1, n - 1)
    frac = idx - lo
    return sv[lo] * (1 - frac) + sv[hi] * frac


def _archetype_power_stats(
    player_results: list[dict[str, Any]],
) -> dict[str, dict[str, float]]:
    """Return {archetype: {median, p10, p90}} of final_power."""
    by_arch: dict[str, list[float]] = {}
    for row in player_results:
        arch = row["archetype"] or "unknown"
        fp = row["final_power"]
        if fp is not None:
            by_arch.setdefault(arch, []).append(fp)
    out: dict[str, dict[str, float]] = {}
    for arch, vals in by_arch.items():
        out[arch] = {
            "median": _pct(vals, 50),
            "p10": _pct(vals, 10),
            "p90": _pct(vals, 90),
        }
    return out


def _archetype_series(
    series_rows: list[dict[str, Any]],
    player_results: list[dict[str, Any]],
) -> dict[str, dict[str, list[Any]]]:
    """Compute per-archetype median/p10/p90 power-over-time curves.

    Returns {archetype: {t_h: [...], median: [...], p10: [...], p90: [...]}}.
    """
    arch_map: dict[tuple[int, int], str] = {
        (r["run_id"], r["player_id"]): (r["archetype"] or "unknown")
        for r in player_results
    }
    # Gather all power values per (archetype, t_h)
    by_arch_t: dict[str, dict[int, list[float]]] = {}
    for s in series_rows:
        key = (s["run_id"], s["player_id"])
        arch = arch_map.get(key, "unknown")
        t = s["t_h"]
        p = s["power"]
        if p is not None:
            by_arch_t.setdefault(arch, {}).setdefault(t, []).append(p)
    out: dict[str, dict[str, list[Any]]] = {}
    for arch, t_map in by_arch_t.items():
        ts = sorted(t_map.keys())
        out[arch] = {
            "t_h": ts,
            "median": [_pct(t_map[t], 50) for t in ts],
            "p10": [_pct(t_map[t], 10) for t in ts],
            "p90": [_pct(t_map[t], 90) for t in ts],
        }
    return out


def _sweep_overview_data(
    runs: list[dict[str, Any]],
    metrics_by_run: dict[int, dict[str, float]],
) -> dict[str, Any]:
    """Build overview table data and optional 2-param heatmap payload."""
    # Determine which params actually vary
    varied_keys: set[str] = set()
    for run in runs:
        v = json.loads(run["varied"] or "{}")
        varied_keys.update(v.keys())
    varied_keys_list = sorted(varied_keys)

    table_rows = []
    for run in runs:
        v = json.loads(run["varied"] or "{}")
        m = metrics_by_run.get(run["run_id"], {})
        row: dict[str, Any] = {
            "run_id": run["run_id"],
            "seed": run["seed"],
            "players": run["players"],
            "wall_s": run["wall_s"],
        }
        for k in varied_keys_list:
            row[f"param_{k}"] = v.get(k)
        row.update(m)
        table_rows.append(row)

    heatmap: dict[str, Any] | None = None
    if len(varied_keys_list) == 2:
        k0, k1 = varied_keys_list
        # Collect all unique values for each param
        vals0: list[Any] = sorted(
            {json.loads(r["varied"] or "{}").get(k0) for r in runs},
            key=lambda x: (x is None, x),
        )
        vals1: list[Any] = sorted(
            {json.loads(r["varied"] or "{}").get(k1) for r in runs},
            key=lambda x: (x is None, x),
        )
        # metric names from all runs
        all_metrics: set[str] = set()
        for m in metrics_by_run.values():
            all_metrics.update(m.keys())
        metric_list = sorted(all_metrics)

        # For each cell (v0, v1) gather run_ids grouped by seed
        # then compute median per metric
        cell_metrics: dict[
            tuple[Any, Any], dict[str, list[float]]
        ] = {}
        for run in runs:
            v = json.loads(run["varied"] or "{}")
            cell = (v.get(k0), v.get(k1))
            m = metrics_by_run.get(run["run_id"], {})
            for mname, mval in m.items():
                cell_metrics.setdefault(cell, {}).setdefault(
                    mname, []
                ).append(mval)

        # Build grid: metric -> list of rows, each row = list of median values
        grids: dict[str, list[list[float | None]]] = {}
        for mname in metric_list:
            grid: list[list[float | None]] = []
            for v0 in vals0:
                row_vals: list[float | None] = []
                for v1 in vals1:
                    cell = (v0, v1)
                    cell_vals = cell_metrics.get(cell, {}).get(
                        mname, []
                    )
                    row_vals.append(
                        _pct(cell_vals, 50) if cell_vals else None
                    )
                grid.append(row_vals)
            grids[mname] = grid

        heatmap = {
            "param0": k0,
            "param1": k1,
            "vals0": [str(v) for v in vals0],
            "vals1": [str(v) for v in vals1],
            "metrics": metric_list,
            "grids": grids,
        }

    return {
        "varied_keys": varied_keys_list,
        "table": table_rows,
        "heatmap": heatmap,
    }


def _evolution_data(
    evo_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Summarise evolution rows into per-gen best/median fitness + best genome."""
    if not evo_rows:
        return {}
    by_gen: dict[int, list[dict[str, Any]]] = {}
    for r in evo_rows:
        by_gen.setdefault(r["gen"], []).append(r)
    gens = sorted(by_gen.keys())
    best_fit = []
    median_fit = []
    best_genomes: dict[int, str] = {}
    for g in gens:
        fits = [r["fitness"] for r in by_gen[g] if r["fitness"] is not None]
        if fits:
            best_fit.append(max(fits))
            median_fit.append(_pct(fits, 50))
            best_row = max(by_gen[g], key=lambda r: r["fitness"] or 0.0)
            best_genomes[g] = best_row["genome"] or "{}"
        else:
            best_fit.append(None)
            median_fit.append(None)
    overall_best = max(
        evo_rows, key=lambda r: r["fitness"] or 0.0, default=None
    )
    return {
        "gens": gens,
        "best_fitness": best_fit,
        "median_fitness": median_fit,
        "best_genome": (
            overall_best["genome"] if overall_best else "{}"
        ),
        "best_gen": (
            overall_best["gen"] if overall_best else None
        ),
    }


def _load_trace(trace_path: str | None) -> dict[str, Any] | None:
    """Load trace JSON from path; return None if path is None or missing."""
    if not trace_path:
        return None
    p = Path(trace_path)
    if not p.exists():
        logger.warning("Trace file not found: %s", trace_path)
        return None
    try:
        with p.open() as fh:
            return json.load(fh)  # type: ignore[no-any-return]
    except Exception:
        logger.exception("Failed to load trace: %s", trace_path)
        return None


def _fetch_map_elites(
    conn: sqlite3.Connection,
) -> dict[str, Any] | None:
    """Fetch MAP-Elites archive data; return None if tables are absent or empty."""
    # Guard: check tables exist
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
            " AND name IN ('map_elites_meta', 'map_elites')"
        )
    }
    if "map_elites_meta" not in tables or "map_elites" not in tables:
        return None

    # Pick the latest me_id
    row = conn.execute(
        "SELECT me_id, x_name, y_name, x_label, y_label,"
        " x_max, y_max, x_bins, y_bins, iterations, evaluations"
        " FROM map_elites_meta ORDER BY me_id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return None

    (
        me_id, x_name, y_name, x_label, y_label,
        x_max, y_max, x_bins, y_bins, iterations, evaluations,
    ) = row

    cells = conn.execute(
        "SELECT cell_x, cell_y, genome, fitness, desc_x, desc_y, found_at"
        " FROM map_elites WHERE me_id = ?",
        (me_id,),
    ).fetchall()

    cell_list = [
        {
            "cell_x": c[0],
            "cell_y": c[1],
            "genome": json.loads(c[2]),
            "fitness": c[3],
            "desc_x": c[4],
            "desc_y": c[5],
            "found_at": c[6],
        }
        for c in cells
    ]

    total_cells = x_bins * y_bins
    filled = len(cell_list)
    coverage = filled / total_cells if total_cells else 0.0
    qd_score = sum(c["fitness"] for c in cell_list)
    best = max(cell_list, key=lambda c: c["fitness"]) if cell_list else None

    # Build list of me_ids for the selector
    all_ids = [
        r[0]
        for r in conn.execute(
            "SELECT me_id FROM map_elites_meta ORDER BY me_id DESC"
        )
    ]

    return {
        "me_id": me_id,
        "all_me_ids": all_ids,
        "x_label": x_label or x_name,
        "y_label": y_label or y_name,
        "x_max": x_max,
        "y_max": y_max,
        "x_bins": x_bins,
        "y_bins": y_bins,
        "iterations": iterations,
        "evaluations": evaluations,
        "cells": cell_list,
        "coverage": coverage,
        "qd_score": qd_score,
        "best_fitness": best["fitness"] if best else None,
        "best_cell_x": best["cell_x"] if best else None,
        "best_cell_y": best["cell_y"] if best else None,
    }


# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------

_CSS = """
:root {
  --bg: #f8f9fa; --bg2: #ffffff; --bg3: #eef0f3;
  --fg: #1a1a2e; --fg2: #444; --accent: #4f6ef7;
  --ok: #22c55e; --fail: #ef4444; --border: #d1d5db;
  --card-shadow: 0 2px 8px rgba(0,0,0,.08);
  --radius: 8px;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0f1117; --bg2: #1a1d27; --bg3: #252836;
    --fg: #e8e9f0; --fg2: #aaa; --accent: #6f8fff;
    --ok: #4ade80; --fail: #f87171; --border: #353848;
    --card-shadow: 0 2px 8px rgba(0,0,0,.4);
  }
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: system-ui, -apple-system, sans-serif;
  background: var(--bg); color: var(--fg); font-size: 15px;
  line-height: 1.5;
}
header {
  background: var(--bg2); border-bottom: 1px solid var(--border);
  padding: 16px 24px; display: flex; align-items: center; gap: 16px;
}
header h1 { font-size: 1.3rem; font-weight: 700; }
header span { color: var(--fg2); font-size: .9rem; }
nav {
  background: var(--bg2); border-bottom: 1px solid var(--border);
  display: flex; gap: 0; padding: 0 24px;
}
nav button {
  background: none; border: none; border-bottom: 3px solid transparent;
  padding: 10px 16px; cursor: pointer; color: var(--fg2);
  font-size: .95rem; font-weight: 500; transition: color .15s;
}
nav button:hover { color: var(--fg); }
nav button.active { color: var(--accent); border-bottom-color: var(--accent); }
.panel { display: none; padding: 24px; max-width: 1200px; margin: 0 auto; }
.panel.active { display: block; }
.card {
  background: var(--bg2); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 20px;
  box-shadow: var(--card-shadow); margin-bottom: 20px;
}
.card h2 { font-size: 1.05rem; font-weight: 600; margin-bottom: 14px; }
table {
  width: 100%; border-collapse: collapse; font-size: .875rem;
  overflow-x: auto; display: block;
}
th {
  text-align: left; padding: 8px 10px; background: var(--bg3);
  border-bottom: 1px solid var(--border); white-space: nowrap;
  font-weight: 600;
}
td { padding: 7px 10px; border-bottom: 1px solid var(--border); }
tr:last-child td { border-bottom: none; }
tr:hover td { background: var(--bg3); }
.badge {
  display: inline-block; padding: 2px 8px; border-radius: 99px;
  font-size: .78rem; font-weight: 600;
}
.badge.ok { background: #dcfce7; color: #166534; }
.badge.fail { background: #fee2e2; color: #991b1b; }
@media (prefers-color-scheme: dark) {
  .badge.ok { background: #14532d; color: #86efac; }
  .badge.fail { background: #450a0a; color: #fca5a5; }
}
select, input[type=range] {
  background: var(--bg3); color: var(--fg); border: 1px solid var(--border);
  border-radius: 4px; padding: 4px 8px; font-size: .9rem;
}
canvas { display: block; max-width: 100%; }
.controls {
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  margin-bottom: 12px;
}
.ctrl-label { font-size: .85rem; color: var(--fg2); }
.row2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
@media (max-width: 700px) { .row2 { grid-template-columns: 1fr; } }
pre {
  background: var(--bg3); border-radius: 6px; padding: 12px;
  font-size: .8rem; overflow-x: auto; white-space: pre-wrap;
}
.me-detail-card {
  position: absolute; pointer-events: none; background: var(--bg2);
  border: 1px solid var(--border); border-radius: var(--radius);
  padding: 10px 14px; font-size: .82rem; min-width: 160px;
  box-shadow: var(--card-shadow); z-index: 10;
}
.me-detail-card table { display: table; font-size: .8rem; }
.me-detail-card td { border-bottom: none; padding: 2px 6px 2px 0; }
.me-stat-line { font-size: .88rem; color: var(--fg2); margin-bottom: 10px; }
.me-stat-line strong { color: var(--fg); }
#me-map-wrap { position: relative; }
"""

_JS = r"""
// ── helpers ─────────────────────────────────────────────────────────────────
const DATA = JSON.parse(document.getElementById('app-data').textContent);

function $(id) { return document.getElementById(id); }
function svgEl(tag, attrs) {
  const el = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [k, v] of Object.entries(attrs || {})) el.setAttribute(k, v);
  return el;
}

// ── tab navigation ───────────────────────────────────────────────────────────
document.querySelectorAll('nav button').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('nav button').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    $(btn.dataset.panel).classList.add('active');
  });
});

// ── colour scheme detection ──────────────────────────────────────────────────
function isDark() {
  return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
}
function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

// ── generic SVG line chart ────────────────────────────────────────────────────
// series: [{label, x:[], y:[], dash, band:{lo:[],hi:[]}, color}]
function lineChart(svgId, series, opts = {}) {
  const svg = $(svgId);
  while (svg.firstChild) svg.removeChild(svg.firstChild);
  const W = svg.clientWidth || 600, H = svg.clientHeight || 260;
  const mg = { t: 20, r: 20, b: 40, l: 60 };
  const pw = W - mg.l - mg.r, ph = H - mg.t - mg.b;

  let xMin = Infinity, xMax = -Infinity, yMin = Infinity, yMax = -Infinity;
  for (const s of series) {
    for (const v of s.x) { xMin = Math.min(xMin, v); xMax = Math.max(xMax, v); }
    for (const v of s.y) { yMin = Math.min(yMin, v); yMax = Math.max(yMax, v); }
    if (s.band) {
      for (const v of s.band.lo) { yMin = Math.min(yMin, v); }
      for (const v of s.band.hi) { yMax = Math.max(yMax, v); }
    }
  }
  if (xMin === xMax) xMax = xMin + 1;
  if (yMin === yMax) yMax = yMin + 1;
  if (opts.yMin !== undefined) yMin = opts.yMin;

  const sx = v => mg.l + (v - xMin) / (xMax - xMin) * pw;
  const sy = v => mg.t + ph - (v - yMin) / (yMax - yMin) * ph;

  const fgColor = cssVar('--fg2');
  const borderColor = cssVar('--border');

  // axes
  const axisG = svgEl('g');
  // y-axis ticks
  const yTicks = 5;
  for (let i = 0; i <= yTicks; i++) {
    const val = yMin + (yMax - yMin) * i / yTicks;
    const y = sy(val);
    const line = svgEl('line', { x1: mg.l, x2: mg.l + pw, y1: y, y2: y,
      stroke: borderColor, 'stroke-width': '1', opacity: '0.5' });
    axisG.appendChild(line);
    const txt = svgEl('text', { x: mg.l - 6, y: y + 4, 'text-anchor': 'end',
      fill: fgColor, 'font-size': '11' });
    txt.textContent = val >= 1e6 ? (val/1e6).toFixed(1)+'M'
      : val >= 1e3 ? (val/1e3).toFixed(1)+'k' : Math.round(val);
    axisG.appendChild(txt);
  }
  // x-axis ticks
  const xTicks = Math.min(8, series[0]?.x.length || 5);
  for (let i = 0; i <= xTicks; i++) {
    const val = xMin + (xMax - xMin) * i / xTicks;
    const x = sx(val);
    const txt = svgEl('text', { x, y: mg.t + ph + 16, 'text-anchor': 'middle',
      fill: fgColor, 'font-size': '11' });
    txt.textContent = Math.round(val);
    axisG.appendChild(txt);
  }
  svg.appendChild(axisG);

  const PALETTE = ['#4f6ef7','#f97316','#22c55e','#a855f7','#06b6d4','#f43f5e','#eab308','#14b8a6'];
  series.forEach((s, si) => {
    const color = s.color || PALETTE[si % PALETTE.length];
    if (s.band) {
      // draw band as polygon
      const ptsFwd = s.x.map((xv, i) => [sx(xv), sy(s.band.hi[i])]);
      const ptsBwd = [...s.x.map((xv, i) => [sx(xv), sy(s.band.lo[i])])].reverse();
      const pts = [...ptsFwd, ...ptsBwd].map(p => p.join(',')).join(' ');
      const poly = svgEl('polygon', { points: pts, fill: color, opacity: '0.18' });
      svg.appendChild(poly);
    }
    if (s.x.length) {
      const d = s.x.map((xv, i) => `${i === 0 ? 'M' : 'L'}${sx(xv)},${sy(s.y[i])}`).join(' ');
      const path = svgEl('path', { d, fill: 'none', stroke: color,
        'stroke-width': '2', 'stroke-dasharray': s.dash || '' });
      svg.appendChild(path);
    }
    // legend entry
    const lx = mg.l + si * 130, ly = H - 6;
    const dot = svgEl('circle', { cx: lx + 6, cy: ly - 4, r: 4, fill: color });
    const ltxt = svgEl('text', { x: lx + 14, y: ly, fill: fgColor, 'font-size': '11' });
    ltxt.textContent = s.label;
    svg.appendChild(dot); svg.appendChild(ltxt);
  });
}

// ── generic SVG bar chart ────────────────────────────────────────────────────
// bars: [{label, value, lo, hi}] (lo/hi optional error bars)
function barChart(svgId, bars, opts = {}) {
  const svg = $(svgId);
  while (svg.firstChild) svg.removeChild(svg.firstChild);
  const W = svg.clientWidth || 600, H = svg.clientHeight || 260;
  const mg = { t: 20, r: 20, b: 60, l: 70 };
  const pw = W - mg.l - mg.r, ph = H - mg.t - mg.b;
  if (!bars.length) return;

  let yMin = 0, yMax = Math.max(...bars.map(b => b.hi ?? b.value));
  if (yMin === yMax) yMax = yMin + 1;

  const sy = v => mg.t + ph - (v - yMin) / (yMax - yMin) * ph;
  const barW = pw / bars.length * 0.6;
  const gap = pw / bars.length;
  const fgColor = cssVar('--fg2');
  const borderColor = cssVar('--border');

  const PALETTE = ['#4f6ef7','#f97316','#22c55e','#a855f7','#06b6d4','#f43f5e','#eab308','#14b8a6'];

  // y-axis ticks
  for (let i = 0; i <= 5; i++) {
    const val = yMin + (yMax - yMin) * i / 5;
    const y = sy(val);
    const line = svgEl('line', { x1: mg.l, x2: mg.l + pw, y1: y, y2: y,
      stroke: borderColor, 'stroke-width': '1', opacity: '0.5' });
    svg.appendChild(line);
    const txt = svgEl('text', { x: mg.l - 6, y: y + 4, 'text-anchor': 'end',
      fill: fgColor, 'font-size': '11' });
    txt.textContent = val >= 1e6 ? (val/1e6).toFixed(1)+'M'
      : val >= 1e3 ? (val/1e3).toFixed(1)+'k' : Math.round(val);
    svg.appendChild(txt);
  }

  bars.forEach((b, i) => {
    const x = mg.l + i * gap + (gap - barW) / 2;
    const yTop = sy(b.value);
    const color = PALETTE[i % PALETTE.length];
    const rect = svgEl('rect', { x, y: yTop, width: barW, height: Math.max(1, sy(yMin) - yTop),
      fill: color, rx: '3' });
    svg.appendChild(rect);
    // error bars
    if (b.lo !== undefined && b.hi !== undefined) {
      const cx = x + barW / 2;
      const line = svgEl('line', { x1: cx, x2: cx, y1: sy(b.hi), y2: sy(b.lo),
        stroke: fgColor, 'stroke-width': '2' });
      const capLo = svgEl('line', { x1: cx - 5, x2: cx + 5, y1: sy(b.lo), y2: sy(b.lo),
        stroke: fgColor, 'stroke-width': '2' });
      const capHi = svgEl('line', { x1: cx - 5, x2: cx + 5, y1: sy(b.hi), y2: sy(b.hi),
        stroke: fgColor, 'stroke-width': '2' });
      svg.appendChild(line); svg.appendChild(capLo); svg.appendChild(capHi);
    }
    // x label
    const txt = svgEl('text', { x: x + barW / 2, y: mg.t + ph + 16,
      'text-anchor': 'middle', fill: fgColor, 'font-size': '11' });
    txt.textContent = b.label;
    svg.appendChild(txt);
  });
}

// ── heatmap ───────────────────────────────────────────────────────────────────
function drawHeatmap(hm, metricIdx) {
  const svg = $('heatmap-svg');
  while (svg.firstChild) svg.removeChild(svg.firstChild);
  if (!hm) return;

  const metric = hm.metrics[metricIdx];
  const grid = hm.grids[metric];
  if (!grid) return;

  const nRows = grid.length, nCols = grid[0].length;
  const W = svg.clientWidth || 500, H = 300;
  svg.setAttribute('height', H);
  const mg = { t: 30, r: 20, b: 40, l: 80 };
  const cellW = (W - mg.l - mg.r) / nCols;
  const cellH = (H - mg.t - mg.b) / nRows;

  // collect non-null values for colour scale
  const allVals = grid.flat().filter(v => v !== null);
  const vMin = allVals.length ? Math.min(...allVals) : 0;
  const vMax = allVals.length ? Math.max(...allVals) : 1;
  const norm = v => vMax === vMin ? 0.5 : (v - vMin) / (vMax - vMin);
  // blue-white-red
  const heat = t => {
    if (t < 0.5) {
      const u = t * 2;
      return `rgb(${Math.round(65 + u*180)},${Math.round(105 + u*150)},${Math.round(225 - u*80)})`;
    } else {
      const u = (t - 0.5) * 2;
      return `rgb(${Math.round(245)},${Math.round(255 - u*200)},${Math.round(145 - u*130)})`;
    }
  };
  const fgColor = cssVar('--fg2');

  for (let r = 0; r < nRows; r++) {
    for (let c = 0; c < nCols; c++) {
      const val = grid[r][c];
      const x = mg.l + c * cellW, y = mg.t + r * cellH;
      const fill = val === null ? cssVar('--bg3') : heat(norm(val));
      const rect = svgEl('rect', { x, y, width: cellW - 1, height: cellH - 1, fill });
      svg.appendChild(rect);
      if (val !== null) {
        const txt = svgEl('text', { x: x + cellW/2, y: y + cellH/2 + 4,
          'text-anchor': 'middle', fill: '#fff', 'font-size': '10',
          'font-weight': '600' });
        txt.textContent = val >= 1e3 ? (val/1e3).toFixed(1)+'k' : val.toFixed(1);
        svg.appendChild(txt);
      }
    }
    // row label
    const lbl = svgEl('text', { x: mg.l - 6, y: mg.t + r * cellH + cellH/2 + 4,
      'text-anchor': 'end', fill: fgColor, 'font-size': '11' });
    lbl.textContent = hm.vals0[r];
    svg.appendChild(lbl);
  }
  // col labels
  for (let c = 0; c < nCols; c++) {
    const txt = svgEl('text', { x: mg.l + c * cellW + cellW/2, y: mg.t + nRows * cellH + 14,
      'text-anchor': 'middle', fill: fgColor, 'font-size': '11' });
    txt.textContent = hm.vals1[c];
    svg.appendChild(txt);
  }
  // axis labels
  const ax0 = svgEl('text', { x: 8, y: mg.t + nRows * cellH / 2, 'text-anchor': 'middle',
    fill: fgColor, 'font-size': '12', transform: `rotate(-90, 8, ${mg.t + nRows * cellH / 2})` });
  ax0.textContent = hm.param0;
  svg.appendChild(ax0);
  const ax1 = svgEl('text', { x: mg.l + nCols * cellW / 2, y: H - 2,
    'text-anchor': 'middle', fill: fgColor, 'font-size': '12' });
  ax1.textContent = hm.param1;
  svg.appendChild(ax1);
}

// ── Panel 1: Sweep overview ──────────────────────────────────────────────────
(function buildSweepPanel() {
  const overview = DATA.overview;
  if (!overview) return;

  // populate table
  const thead = $('sweep-thead'), tbody = $('sweep-tbody');
  const cols = overview.varied_keys.map(k => 'param_' + k)
    .concat(['run_id', 'seed', 'players', 'wall_s']);
  // add metric cols from first row
  const metricCols = overview.table.length
    ? Object.keys(overview.table[0]).filter(k => !cols.includes(k)) : [];
  const allCols = cols.concat(metricCols);

  const trh = document.createElement('tr');
  for (const c of allCols) {
    const th = document.createElement('th');
    th.textContent = c.replace('param_', '★ ');
    trh.appendChild(th);
  }
  thead.appendChild(trh);

  for (const row of overview.table) {
    const tr = document.createElement('tr');
    for (const c of allCols) {
      const td = document.createElement('td');
      const v = row[c];
      td.textContent = (typeof v === 'number') ? +v.toFixed(3) : (v ?? '—');
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }

  // heatmap
  const hm = overview.heatmap;
  if (hm) {
    $('heatmap-section').style.display = '';
    const sel = $('heatmap-metric-sel');
    for (const m of hm.metrics) {
      const opt = document.createElement('option');
      opt.value = m; opt.textContent = m;
      sel.appendChild(opt);
    }
    const render = () => drawHeatmap(hm, sel.selectedIndex);
    sel.addEventListener('change', render);
    setTimeout(render, 50);
  }
})();

// ── Panel 2: Archetype ────────────────────────────────────────────────────────
(function buildArchPanel() {
  const ap = DATA.archetype;
  if (!ap) return;

  // bar chart
  const archs = Object.keys(ap.power_stats);
  const bars = archs.map(a => ({
    label: a,
    value: ap.power_stats[a].median,
    lo: ap.power_stats[a].p10,
    hi: ap.power_stats[a].p90,
  }));
  setTimeout(() => barChart('arch-bar-svg', bars), 50);

  // line chart per archetype
  const series = archs.map(a => {
    const d = ap.series[a];
    if (!d) return null;
    return {
      label: a,
      x: d.t_h,
      y: d.median,
      band: { lo: d.p10, hi: d.p90 },
    };
  }).filter(Boolean);
  setTimeout(() => lineChart('arch-line-svg', series, { yMin: 0 }), 50);
})();

// ── Panel 3: Invariants ───────────────────────────────────────────────────────
(function buildInvPanel() {
  const inv = DATA.invariants;
  if (!inv) return;
  const tbody = $('inv-summary-tbody');
  for (const [name, counts] of Object.entries(inv.summary)) {
    const tr = document.createElement('tr');
    const tdName = document.createElement('td'); tdName.textContent = name;
    const tdOk = document.createElement('td');
    tdOk.innerHTML = `<span class="badge ok">${counts.ok} pass</span>`;
    const tdFail = document.createElement('td');
    if (counts.fail > 0)
      tdFail.innerHTML = `<span class="badge fail">${counts.fail} fail</span>`;
    else tdFail.innerHTML = `<span class="badge ok">0 fail</span>`;
    tr.appendChild(tdName); tr.appendChild(tdOk); tr.appendChild(tdFail);
    tbody.appendChild(tr);
  }

  const ftbody = $('inv-fail-tbody');
  for (const row of inv.failing) {
    const tr = document.createElement('tr');
    for (const v of [row.run_id, row.name, row.detail]) {
      const td = document.createElement('td');
      td.textContent = v ?? '—';
      tr.appendChild(td);
    }
    ftbody.appendChild(tr);
  }
})();

// ── Panel 4: Evolution ────────────────────────────────────────────────────────
(function buildEvoPanel() {
  const evo = DATA.evolution;
  if (!evo || !evo.gens || !evo.gens.length) {
    const section = $('evo-panel');
    if (section) section.style.display = 'none';
    const btn = document.querySelector('[data-panel="evo-panel"]');
    if (btn) btn.style.display = 'none';
    return;
  }
  const series = [
    { label: 'Best', x: evo.gens, y: evo.best_fitness },
    { label: 'Median', x: evo.gens, y: evo.median_fitness, dash: '5,4' },
  ];
  setTimeout(() => lineChart('evo-line-svg', series, { yMin: 0 }), 50);
  $('evo-best-genome').textContent = JSON.stringify(
    JSON.parse(evo.best_genome || '{}'), null, 2
  );
  if (evo.best_gen !== null)
    $('evo-best-gen').textContent = `Generation ${evo.best_gen}`;
})();

// ── Panel 5: Map replay ────────────────────────────────────────────────────────
(function buildMapPanel() {
  const traces = DATA.traces;
  if (!traces || !traces.length) {
    const section = $('map-panel');
    if (section) section.style.display = 'none';
    const btn = document.querySelector('[data-panel="map-panel"]');
    if (btn) btn.style.display = 'none';
    return;
  }

  const sel = $('trace-run-sel');
  for (const t of traces) {
    const opt = document.createElement('option');
    opt.value = t.meta.run_id;
    opt.textContent = `Run ${t.meta.run_id} – seed ${t.meta.seed}`;
    sel.appendChild(opt);
  }

  let animHandle = null;
  let currentH = 0;
  let playing = false;

  function traceByRunId(id) {
    return traces.find(t => String(t.meta.run_id) === String(id));
  }

  function drawMap(trace, h) {
    const canvas = $('map-canvas');
    const ctx = canvas.getContext('2d');
    const W = canvas.width, H = canvas.height;
    ctx.clearRect(0, 0, W, H);

    const radius = trace.meta.radius || 26;
    const legendW = 260;
    const cx = legendW + (W - legendW) / 2, cy = H / 2;
    const scale = Math.min(W - legendW, H) / 2 / (radius + 1.5);

    // background disc
    ctx.save();
    ctx.beginPath();
    ctx.arc(cx, cy, radius * scale, 0, Math.PI * 2);
    ctx.fillStyle = isDark() ? '#1e2130' : '#e8ecf4';
    ctx.fill();
    ctx.strokeStyle = isDark() ? '#3a3f5c' : '#c0c8d8';
    ctx.lineWidth = 1;
    ctx.stroke();
    ctx.restore();

    // player colour map
    const players = trace.meta.players || [];
    const PALETTE = ['#4f6ef7','#f97316','#22c55e','#a855f7','#06b6d4',
                     '#f43f5e','#eab308','#14b8a6','#8b5cf6','#ec4899'];
    const playerColor = {};
    players.forEach((p, i) => {
      playerColor[p.id] = PALETTE[(p.color_key || i) % PALETTE.length];
    });
    playerColor[0] = isDark() ? '#555' : '#aaa'; // NPC

    // bases active at hour h
    const activeBases = (trace.bases || []).filter(
      b => b.from_h <= h && (b.to_h === null || b.to_h > h)
    );
    for (const base of activeBases) {
      const bx = cx + base.x * scale;
      const by = cy + base.y * scale;
      const r = base.kind === 'player' ? 7 : base.kind === 'site' ? 8 : 5;
      ctx.beginPath();
      if (base.kind === 'site') {
        // diamond
        ctx.moveTo(bx, by - r); ctx.lineTo(bx + r, by);
        ctx.lineTo(bx, by + r); ctx.lineTo(bx - r, by);
        ctx.closePath();
      } else {
        ctx.arc(bx, by, r, 0, Math.PI * 2);
      }
      const owner = base.owner || 0;
      ctx.fillStyle = playerColor[owner] || '#999';
      ctx.fill();
      ctx.strokeStyle = isDark() ? '#fff' : '#333';
      ctx.lineWidth = 1;
      ctx.stroke();
    }

    // marches: moving dot between depart_h and return_h
    for (const march of (trace.marches || [])) {
      const { from, to, depart_h, arrive_h, return_h, owner } = march;
      if (h < depart_h || h > (return_h || arrive_h)) continue;
      let t, fx, fy, tx, ty;
      if (h <= arrive_h) {
        t = (h - depart_h) / Math.max(0.01, arrive_h - depart_h);
        fx = from[0]; fy = from[1]; tx = to[0]; ty = to[1];
      } else {
        t = (h - arrive_h) / Math.max(0.01, (return_h || arrive_h) - arrive_h);
        fx = to[0]; fy = to[1]; tx = from[0]; ty = from[1];
      }
      const mx = cx + (fx + (tx - fx) * t) * scale;
      const my = cy + (fy + (ty - fy) * t) * scale;
      ctx.beginPath();
      ctx.arc(mx, my, 4, 0, Math.PI * 2);
      ctx.fillStyle = playerColor[owner] || '#fff';
      ctx.fill();
      ctx.strokeStyle = isDark() ? '#fff' : '#000';
      ctx.lineWidth = 1;
      ctx.stroke();
    }

    // battles flash if within ±0.5 h of h
    for (const battle of (trace.battles || [])) {
      if (Math.abs(battle.t_h - h) > 0.5) continue;
      const bx = cx + battle.x * scale;
      const by = cy + battle.y * scale;
      ctx.beginPath();
      ctx.arc(bx, by, 10, 0, Math.PI * 2);
      ctx.strokeStyle = battle.attacker_won ? '#f59e0b' : '#ef4444';
      ctx.lineWidth = 3;
      ctx.stroke();
    }

    // legend
    let li = 0;
    const rowsPerCol = Math.max(1, Math.floor((H - 16) / 18));
    for (const p of players) {
      const lx = 12 + Math.floor(li / rowsPerCol) * 125;
      const ly = 16 + (li % rowsPerCol) * 18;
      ctx.beginPath();
      ctx.arc(lx + 6, ly, 5, 0, Math.PI * 2);
      ctx.fillStyle = playerColor[p.id] || '#999';
      ctx.fill();
      ctx.fillStyle = isDark() ? '#e8e9f0' : '#1a1a2e';
      ctx.font = '11px system-ui, sans-serif';
      ctx.fillText(`P${p.id} ${p.archetype || ''}`, lx + 14, ly + 4);
      li++;
    }

    // hour label
    ctx.fillStyle = isDark() ? '#aaa' : '#555';
    ctx.font = '12px system-ui, sans-serif';
    ctx.textAlign = 'right';
    ctx.fillText(`h=${h.toFixed(1)}  d=${(h/24).toFixed(1)}`, W - 10, H - 8);
    ctx.textAlign = 'left';
  }

  function maxH(trace) {
    return (trace.meta.days || 28) * 24;
  }

  function renderCurrent() {
    const trace = traceByRunId(sel.value);
    if (!trace) return;
    driveH(trace, currentH);
  }

  function driveH(trace, h) {
    currentH = h;
    const scrubber = $('map-scrubber');
    scrubber.value = h;
    $('map-h-label').textContent = `h ${h.toFixed(0)} / d ${(h/24).toFixed(1)}`;
    drawMap(trace, h);
  }

  function startPlay() {
    playing = true;
    $('map-play-btn').textContent = '⏸';
    const trace = traceByRunId(sel.value);
    if (!trace) return;
    const total = maxH(trace);
    const step = total / 300; // ~300 frames
    function tick() {
      if (!playing) return;
      currentH = Math.min(currentH + step, total);
      driveH(trace, currentH);
      if (currentH < total) animHandle = requestAnimationFrame(tick);
      else { playing = false; $('map-play-btn').textContent = '▶'; }
    }
    animHandle = requestAnimationFrame(tick);
  }

  function stopPlay() {
    playing = false;
    if (animHandle) cancelAnimationFrame(animHandle);
    $('map-play-btn').textContent = '▶';
  }

  $('map-play-btn').addEventListener('click', () => {
    if (playing) stopPlay(); else startPlay();
  });

  $('map-scrubber').addEventListener('input', () => {
    stopPlay();
    const trace = traceByRunId(sel.value);
    if (!trace) return;
    driveH(trace, +$('map-scrubber').value);
  });

  sel.addEventListener('change', () => {
    stopPlay();
    currentH = 0;
    const trace = traceByRunId(sel.value);
    if (!trace) return;
    $('map-scrubber').max = maxH(trace);
    renderCurrent();
  });

  // init first trace
  if (traces.length) {
    const trace = traces[0];
    $('map-scrubber').max = maxH(trace);
    drawMap(trace, 0);
  }
})();

// ── Panel 6: Strategy Map (MAP-Elites) ───────────────────────────────────────
(function buildStrategyMapPanel() {
  const me = DATA.map_elites;
  const panel = $('panel-strategy-map');
  if (!panel) return;

  if (!me || !me.cells || !me.cells.length) {
    // empty-state already rendered in HTML; nothing more to do
    return;
  }

  // ── me_id selector ─────────────────────────────────────────────────────────
  const meSel = $('me-id-sel');
  for (const id of me.all_me_ids) {
    const opt = document.createElement('option');
    opt.value = id; opt.textContent = `Archive ${id}`;
    if (id === me.me_id) opt.selected = true;
    meSel.appendChild(opt);
  }
  // NOTE: switching archive IDs requires a page reload with a new query param;
  // for now selecting a different id is a no-op (data is pre-embedded for latest).

  // ── stats line ─────────────────────────────────────────────────────────────
  const pct = (me.coverage * 100).toFixed(1);
  const qd  = me.qd_score.toFixed(3);
  const bf  = me.best_fitness != null ? me.best_fitness.toFixed(4) : '—';
  const bc  = me.best_cell_x != null ? `(${me.best_cell_x}, ${me.best_cell_y})` : '—';
  $('me-stats-line').innerHTML =
    `Coverage: <strong>${pct}%</strong> &nbsp;|&nbsp; ` +
    `QD-score: <strong>${qd}</strong> &nbsp;|&nbsp; ` +
    `Best fitness: <strong>${bf}</strong> at cell ${bc} &nbsp;|&nbsp; ` +
    `Iterations: <strong>${me.iterations ?? '—'}</strong> &nbsp;` +
    `Evaluations: <strong>${me.evaluations ?? '—'}</strong>`;

  // ── heatmap ─────────────────────────────────────────────────────────────────
  const svg = $('me-heatmap-svg');
  if (!svg) return;

  const xBins = me.x_bins, yBins = me.y_bins;
  const xMax  = me.x_max,  yMax  = me.y_max;

  // index cells into a grid (x = col, y = row; y increasing upward → row = yBins-1-cell_y)
  const grid = Array.from({ length: yBins }, () => Array(xBins).fill(null));
  for (const c of me.cells) {
    const row = yBins - 1 - c.cell_y;
    grid[row][c.cell_x] = c;
  }

  const W = svg.clientWidth || 600;
  const mg = { t: 30, r: 20, b: 50, l: 60 };
  const plotW = W - mg.l - mg.r;
  const plotH = Math.max(200, Math.min(plotW, 480));
  const H = plotH + mg.t + mg.b;
  svg.setAttribute('height', H);
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);

  const cellW = plotW / xBins;
  const cellH = plotH / yBins;
  const fgColor = cssVar('--fg2');
  const borderColor = cssVar('--border');

  // diverging colour scale centred at 1.0
  // below 1 → cool (blue), above 1 → warm (red), 1.0 = neutral grey-white
  function meColor(fitness) {
    const pivot = 1.0;
    const span  = 0.5; // half-range for saturation
    if (fitness <= pivot) {
      const t = Math.min(1, (pivot - fitness) / span);
      // white → steel-blue
      const r = Math.round(255 - t * 185);
      const g = Math.round(255 - t * 145);
      const b = Math.round(255 - t * 30);
      return `rgb(${r},${g},${b})`;
    } else {
      const t = Math.min(1, (fitness - pivot) / span);
      // white → firebrick
      const r = Math.round(255);
      const g = Math.round(255 - t * 210);
      const b = Math.round(255 - t * 210);
      return `rgb(${r},${g},${b})`;
    }
  }

  // hatching pattern for empty cells
  const defs = svgEl('defs');
  const pat = svgEl('pattern', {
    id: 'me-hatch', patternUnits: 'userSpaceOnUse',
    width: '6', height: '6',
  });
  const pl1 = svgEl('line', { x1: '0', y1: '6', x2: '6', y2: '0',
    stroke: borderColor, 'stroke-width': '1', opacity: '0.5' });
  pat.appendChild(pl1);
  defs.appendChild(pat);
  svg.appendChild(defs);

  const cellGroup = svgEl('g');
  svg.appendChild(cellGroup);

  function renderGrid() {
    while (cellGroup.firstChild) cellGroup.removeChild(cellGroup.firstChild);
    for (let row = 0; row < yBins; row++) {
      for (let col = 0; col < xBins; col++) {
        const cell = grid[row][col];
        const x = mg.l + col * cellW;
        const y = mg.t + row * cellH;
        if (cell === null) {
          // empty: hatched grey background
          const bg = svgEl('rect', {
            x, y, width: cellW - 1, height: cellH - 1,
            fill: cssVar('--bg3'),
          });
          cellGroup.appendChild(bg);
          const hatch = svgEl('rect', {
            x, y, width: cellW - 1, height: cellH - 1,
            fill: 'url(#me-hatch)',
          });
          cellGroup.appendChild(hatch);
        } else {
          const fill = meColor(cell.fitness);
          const rect = svgEl('rect', {
            x, y, width: cellW - 1, height: cellH - 1, fill,
            stroke: cell.fitness > 1.3 ? '#f59e0b' : 'none',
            'stroke-width': cell.fitness > 1.3 ? '2' : '0',
          });
          rect.dataset.cx = col;
          rect.dataset.cy = yBins - 1 - row;
          rect.style.cursor = 'pointer';
          cellGroup.appendChild(rect);
          // fitness label for larger cells
          if (cellW > 22 && cellH > 14) {
            const txt = svgEl('text', {
              x: x + cellW / 2, y: y + cellH / 2 + 4,
              'text-anchor': 'middle', fill: '#333', 'font-size': '9',
            });
            txt.textContent = cell.fitness.toFixed(2);
            cellGroup.appendChild(txt);
          }
        }
      }
    }
  }
  renderGrid();

  // axis ticks ────────────────────────────────────────────────────────────────
  // x-axis: bin edges 0 … x_max
  for (let i = 0; i <= xBins; i++) {
    const val = (xMax / xBins * i).toFixed(2);
    const x = mg.l + i * cellW;
    const tick = svgEl('line', { x1: x, y1: mg.t + plotH, x2: x, y2: mg.t + plotH + 4,
      stroke: fgColor, 'stroke-width': '1' });
    svg.appendChild(tick);
    if (i % Math.max(1, Math.floor(xBins / 6)) === 0) {
      const lbl = svgEl('text', { x, y: mg.t + plotH + 16,
        'text-anchor': 'middle', fill: fgColor, 'font-size': '10' });
      lbl.textContent = val;
      svg.appendChild(lbl);
    }
  }
  // y-axis: bin edges 0 … y_max (y increases upward → bottom=0)
  for (let i = 0; i <= yBins; i++) {
    const val = (yMax / yBins * i).toFixed(2);
    const y = mg.t + plotH - i * cellH;
    const tick = svgEl('line', { x1: mg.l - 4, y1: y, x2: mg.l, y2: y,
      stroke: fgColor, 'stroke-width': '1' });
    svg.appendChild(tick);
    if (i % Math.max(1, Math.floor(yBins / 6)) === 0) {
      const lbl = svgEl('text', { x: mg.l - 6, y: y + 4,
        'text-anchor': 'end', fill: fgColor, 'font-size': '10' });
      lbl.textContent = val;
      svg.appendChild(lbl);
    }
  }
  // axis labels
  const xLbl = svgEl('text', { x: mg.l + plotW / 2, y: H - 4,
    'text-anchor': 'middle', fill: fgColor, 'font-size': '12' });
  xLbl.textContent = me.x_label;
  svg.appendChild(xLbl);
  const yMid = mg.t + plotH / 2;
  const yLblEl = svgEl('text', { x: 10, y: yMid,
    'text-anchor': 'middle', fill: fgColor, 'font-size': '12',
    transform: `rotate(-90, 10, ${yMid})` });
  yLblEl.textContent = me.y_label;
  svg.appendChild(yLblEl);

  // colour legend bar (cool…neutral…warm)
  const legX = mg.l + plotW + 4, legY = mg.t, legH = plotH, legW = 12;
  for (let i = 0; i < legH; i++) {
    const t = 1 - i / legH; // t=1 at top (high fitness)
    const fitness = 1.0 + (t - 0.5) * 1.0; // maps 0-1 to 0.5-1.5
    const seg = svgEl('rect', { x: legX, y: legY + i, width: legW, height: 1,
      fill: meColor(fitness) });
    svg.appendChild(seg);
  }
  const legBorder = svgEl('rect', { x: legX, y: legY, width: legW, height: legH,
    fill: 'none', stroke: borderColor, 'stroke-width': '1' });
  svg.appendChild(legBorder);
  ['1.5+', '1.0', '0.5-'].forEach((lbl, li) => {
    const ly = legY + li * legH / 2;
    const lt = svgEl('text', { x: legX + legW + 4, y: ly + 4,
      fill: fgColor, 'font-size': '9' });
    lt.textContent = lbl;
    svg.appendChild(lt);
  });

  // ── detail card on click / hover ────────────────────────────────────────────
  const card = $('me-detail-card');
  const wrap = $('me-map-wrap');

  function showCard(cellData, screenX, screenY) {
    if (!cellData) { card.style.display = 'none'; return; }
    const wrapRect = wrap.getBoundingClientRect();
    let cx = screenX - wrapRect.left + 12;
    let cy = screenY - wrapRect.top + 12;

    const genome = cellData.genome || {};
    const genomeRows = Object.entries(genome)
      .map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join('');

    const binEdgeX0 = (cellData.cell_x * me.x_max / me.x_bins).toFixed(3);
    const binEdgeX1 = ((cellData.cell_x + 1) * me.x_max / me.x_bins).toFixed(3);
    const binEdgeY0 = (cellData.cell_y * me.y_max / me.y_bins).toFixed(3);
    const binEdgeY1 = ((cellData.cell_y + 1) * me.y_max / me.y_bins).toFixed(3);

    card.innerHTML =
      `<strong>Cell (${cellData.cell_x}, ${cellData.cell_y})</strong><br>` +
      `${me.x_label}: [${binEdgeX0}, ${binEdgeX1})<br>` +
      `${me.y_label}: [${binEdgeY0}, ${binEdgeY1})<br>` +
      `desc_x: ${cellData.desc_x?.toFixed(4) ?? '—'}` +
      `&nbsp; desc_y: ${cellData.desc_y?.toFixed(4) ?? '—'}<br>` +
      `<strong>Fitness: ${cellData.fitness.toFixed(4)}</strong>` +
      (cellData.fitness > 1.3 ? ' ★' : '') + `<br>` +
      `Found at eval #${cellData.found_at ?? '—'}<br>` +
      `<br><em>Genome</em><table>${genomeRows}</table>`;

    card.style.display = 'block';
    // clamp so card doesn't overflow wrap width
    const cw = card.offsetWidth || 180;
    if (cx + cw > wrapRect.width - 4) cx = screenX - wrapRect.left - cw - 12;
    card.style.left = cx + 'px';
    card.style.top  = cy + 'px';
  }

  function cellDataAt(col, row_visual) {
    // row_visual is cell_y in grid coords (0=bottom of SVG → y increases upward)
    const row = yBins - 1 - row_visual;
    return grid[row]?.[col] ?? null;
  }

  // Convert a pointer event to viewBox coordinates (the SVG is scaled).
  function cellAt(e) {
    const ctm = svg.getScreenCTM();
    if (!ctm) return null;
    const pt = new DOMPoint(e.clientX, e.clientY).matrixTransform(ctm.inverse());
    const col = Math.floor((pt.x - mg.l) / cellW);
    const rowVis = Math.floor((pt.y - mg.t) / cellH);
    if (col < 0 || col >= xBins || rowVis < 0 || rowVis >= yBins) return null;
    return cellDataAt(col, yBins - 1 - rowVis);
  }

  svg.addEventListener('mousemove', e => showCard(cellAt(e), e.clientX, e.clientY));
  svg.addEventListener('mouseleave', () => { card.style.display = 'none'; });
  svg.addEventListener('click', e => {
    const data = cellAt(e);
    if (data) showCard(data, e.clientX, e.clientY);
  });
})();
"""


def _safe_json(obj: Any) -> str:
    """JSON-encode obj and escape </script> sequences."""
    raw = json.dumps(obj, separators=(",", ":"))
    # Escape </ to prevent early </script> termination
    return raw.replace("</", r"<\/")


def _build_html(
    sweeps: list[dict[str, Any]],
    runs: list[dict[str, Any]],
    metrics_by_run: dict[int, dict[str, float]],
    player_results: list[dict[str, Any]],
    series_rows: list[dict[str, Any]],
    invariant_rows: list[dict[str, Any]],
    evo_rows: list[dict[str, Any]],
    traces: list[dict[str, Any]],
    map_elites_data: dict[str, Any] | None = None,
) -> str:
    """Assemble all data and return the complete HTML string."""
    # ── overview ──────────────────────────────────────────────────────────
    run_ids = [r["run_id"] for r in runs]
    overview = _sweep_overview_data(runs, metrics_by_run)

    # ── archetype ─────────────────────────────────────────────────────────
    arch_power = _archetype_power_stats(player_results)
    arch_series = _archetype_series(series_rows, player_results)
    archetype_data = {
        "power_stats": arch_power,
        "series": arch_series,
    }

    # ── invariants ────────────────────────────────────────────────────────
    inv_summary: dict[str, dict[str, int]] = {}
    for row in invariant_rows:
        name = row["name"]
        bucket = inv_summary.setdefault(name, {"ok": 0, "fail": 0})
        if row["ok"]:
            bucket["ok"] += 1
        else:
            bucket["fail"] += 1
    failing = [r for r in invariant_rows if not r["ok"]]
    invariant_data = {"summary": inv_summary, "failing": failing}

    # ── evolution ─────────────────────────────────────────────────────────
    evo_data = _evolution_data(evo_rows)

    # ── page meta ─────────────────────────────────────────────────────────
    sweep_names = ", ".join(s["name"] or f"sweep {s['sweep_id']}" for s in sweeps)
    title = f"Outpost dashboard — {sweep_names}" if sweep_names else "Outpost dashboard"

    # ── payload ───────────────────────────────────────────────────────────
    payload: dict[str, Any] = {
        "run_count": len(run_ids),
        "overview": overview,
        "archetype": archetype_data,
        "invariants": invariant_data,
        "evolution": evo_data,
        "traces": traces,
        "map_elites": map_elites_data,
    }

    has_evo = bool(evo_rows)
    has_traces = bool(traces)

    tabs: list[tuple[str, str]] = [
        ("sweep-panel", "Sweep overview"),
        ("arch-panel", "Archetypes"),
        ("inv-panel", "Invariants"),
    ]
    if has_evo:
        tabs.append(("evo-panel", "Evolution"))
    if has_traces:
        tabs.append(("map-panel", "Map replay"))
    tabs.append(("panel-strategy-map", "Strategy map"))

    def _nav_btn(i: int, pid: str, label: str) -> str:
        cls = ' class="active"' if i == 0 else ""
        return f'<button data-panel="{pid}"{cls}>{label}</button>'

    nav_html = "\n".join(
        _nav_btn(i, pid, label) for i, (pid, label) in enumerate(tabs)
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{_CSS}</style>
</head>
<body>
<header>
  <h1>Outpost</h1>
  <span>{sweep_names or "all sweeps"} &mdash; {len(run_ids)} runs</span>
</header>
<nav id="main-nav">
{nav_html}
</nav>

<!-- Sweep overview panel -->
<section id="sweep-panel" class="panel active">
  <div class="card">
    <h2>Run table</h2>
    <table>
      <thead id="sweep-thead"></thead>
      <tbody id="sweep-tbody"></tbody>
    </table>
  </div>
  <div class="card" id="heatmap-section" style="display:none">
    <h2>Heatmap</h2>
    <div class="controls">
      <span class="ctrl-label">Metric:</span>
      <select id="heatmap-metric-sel"></select>
    </div>
    <svg id="heatmap-svg" width="100%" height="300" viewBox="0 0 600 300"
         preserveAspectRatio="xMidYMid meet"></svg>
  </div>
</section>

<!-- Archetype panel -->
<section id="arch-panel" class="panel">
  <div class="card">
    <h2>Median final power per archetype (p10–p90)</h2>
    <svg id="arch-bar-svg" width="100%" height="260"
         viewBox="0 0 700 260" preserveAspectRatio="xMidYMid meet"></svg>
  </div>
  <div class="card">
    <h2>Power over time</h2>
    <svg id="arch-line-svg" width="100%" height="280"
         viewBox="0 0 700 280" preserveAspectRatio="xMidYMid meet"></svg>
  </div>
</section>

<!-- Invariants panel -->
<section id="inv-panel" class="panel">
  <div class="card">
    <h2>Pass / fail counts</h2>
    <table>
      <thead>
        <tr><th>Invariant</th><th>Pass</th><th>Fail</th></tr>
      </thead>
      <tbody id="inv-summary-tbody"></tbody>
    </table>
  </div>
  <div class="card">
    <h2>Failing runs</h2>
    <table>
      <thead>
        <tr><th>run_id</th><th>name</th><th>detail</th></tr>
      </thead>
      <tbody id="inv-fail-tbody"></tbody>
    </table>
  </div>
</section>

<!-- Evolution panel -->
<section id="evo-panel" class="panel">
  <div class="card">
    <h2>Fitness over generations</h2>
    <svg id="evo-line-svg" width="100%" height="280"
         viewBox="0 0 700 280" preserveAspectRatio="xMidYMid meet"></svg>
  </div>
  <div class="card row2">
    <div>
      <h2>Best genome <span id="evo-best-gen" style="font-weight:400"></span></h2>
      <pre id="evo-best-genome"></pre>
    </div>
  </div>
</section>

<!-- Map replay panel -->
<section id="map-panel" class="panel">
  <div class="card">
    <div class="controls">
      <span class="ctrl-label">Run:</span>
      <select id="trace-run-sel"></select>
      <button id="map-play-btn">&#9654;</button>
      <input type="range" id="map-scrubber" min="0" max="672" step="0.5"
             value="0" style="flex:1;min-width:120px">
      <span id="map-h-label" class="ctrl-label">h 0</span>
    </div>
    <canvas id="map-canvas" width="900" height="560"
            style="border:1px solid var(--border);border-radius:var(--radius);
                   width:100%;max-width:900px;margin:0 auto;display:block">
    </canvas>
  </div>
</section>

<!-- Strategy map panel (MAP-Elites) -->
<section id="panel-strategy-map" class="panel">
  <div class="card">
    <div class="controls">
      <span class="ctrl-label">Archive:</span>
      <select id="me-id-sel"></select>
    </div>
    <p class="me-stat-line" id="me-stats-line">
      Run <code>python -m app.outpost.sim map</code> to fill this
    </p>
    <div id="me-map-wrap">
      <svg id="me-heatmap-svg" width="100%" height="400"
           viewBox="0 0 600 400"
           preserveAspectRatio="xMidYMid meet"></svg>
      <div id="me-detail-card" class="me-detail-card" style="display:none"></div>
    </div>
  </div>
</section>

<script type="application/json" id="app-data">{_safe_json(payload)}</script>
<script>{_JS}</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_dashboard(
    db_path: Path,
    out_path: Path,
    *,
    sweep_id: int | None = None,
) -> Path:
    """Read *db_path* and write a self-contained HTML dashboard to *out_path*.

    Parameters
    ----------
    db_path:
        Path to the Outpost results SQLite database.
    out_path:
        Destination path for the rendered HTML file.
    sweep_id:
        When given, restrict the report to this sweep only.

    Returns
    -------
    Path
        The resolved path of the written HTML file (same as *out_path*).
    """
    logger.info("Building dashboard from %s (sweep_id=%s)", db_path, sweep_id)
    conn = sqlite3.connect(db_path)
    conn.row_factory = None
    try:
        sweeps = _fetch_sweeps(conn, sweep_id)
        if not sweeps:
            logger.warning(
                "No sweeps found%s",
                f" for sweep_id={sweep_id}" if sweep_id is not None else "",
            )
        sweep_ids = [s["sweep_id"] for s in sweeps]
        runs = _fetch_runs(conn, sweep_ids) if sweep_ids else []
        run_ids = [r["run_id"] for r in runs]
        metrics_by_run = _fetch_metrics(conn, run_ids)
        player_results = _fetch_player_results(conn, run_ids)
        series_rows = _fetch_series(conn, run_ids)
        invariant_rows = _fetch_invariants(conn, run_ids)
        evo_rows = _fetch_evolution(conn)
        map_elites_data = _fetch_map_elites(conn)
    finally:
        conn.close()

    # Load trace files for runs that have one
    traces: list[dict[str, Any]] = []
    for run in runs:
        trace = _load_trace(run["trace_path"])
        if trace is not None:
            traces.append(trace)

    html = _build_html(
        sweeps=sweeps,
        runs=runs,
        metrics_by_run=metrics_by_run,
        player_results=player_results,
        series_rows=series_rows,
        invariant_rows=invariant_rows,
        evo_rows=evo_rows,
        traces=traces,
        map_elites_data=map_elites_data,
    )

    out_path = out_path.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    logger.info("Dashboard written to %s (%d bytes)", out_path, len(html))
    return out_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point for ``python -m app.outpost.sim.dashboard``."""
    parser = argparse.ArgumentParser(
        description="Build an Outpost simulation dashboard."
    )
    parser.add_argument("--db", required=True, type=Path, help="results.sqlite")
    parser.add_argument("--out", required=True, type=Path, help="report.html")
    parser.add_argument("--sweep", type=int, default=None, help="sweep_id")
    args = parser.parse_args()
    out = build_dashboard(args.db, args.out, sweep_id=args.sweep)
    print(out)


if __name__ == "__main__":
    main()
