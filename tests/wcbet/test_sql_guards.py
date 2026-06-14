"""Guards against SQL that is valid Python but rejected by Postgres.

These catch the class of bug where a query string compiles fine and the
unit-test fakes never execute it, so the breakage only shows up against a
real database in production (see the parlay-settlement crash:
``FOR UPDATE is not allowed with DISTINCT clause``).
"""
from __future__ import annotations

import re
from pathlib import Path

DB_DIR = Path(__file__).resolve().parents[2] / "db"

# Split a .py file into the contents of its triple-quoted string literals,
# which is where the SQL lives.
_TRIPLE_QUOTED = re.compile(r"'''(.*?)'''|\"\"\"(.*?)\"\"\"", re.DOTALL)


def _sql_blocks(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    blocks: list[str] = []
    for a, b in _TRIPLE_QUOTED.findall(text):
        blocks.append(a or b)
    return blocks


def test_no_for_update_with_distinct_in_db_layer():
    """Postgres forbids FOR UPDATE together with DISTINCT (or GROUP BY).

    Any query that locks rows (`FOR UPDATE`) must not also be a `DISTINCT`
    select. Scans every SQL block in the db/ layer.
    """
    offenders: list[str] = []
    for py_file in DB_DIR.glob("*.py"):
        for block in _sql_blocks(py_file):
            upper = block.upper()
            if "FOR UPDATE" in upper and "DISTINCT" in upper:
                offenders.append(f"{py_file.name}: {' '.join(block.split())[:120]}")
    assert not offenders, "FOR UPDATE + DISTINCT is invalid in Postgres:\n" + "\n".join(offenders)
