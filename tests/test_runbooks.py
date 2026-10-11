"""Runbooks stay indexed in AGENTS.md and don't point at files that no longer exist."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
RUNBOOKS = sorted((ROOT / "runbooks").glob("*.md"))

_FENCE = re.compile(r"```.*?```", re.DOTALL)
_INLINE = re.compile(r"`([^`\s<>*{}()=:$]+)`")
_FILE_SUFFIXES = (".md", ".py", ".sh", ".json", ".yml", ".toml")


def _mentioned_paths(text: str) -> set[str]:
    """Inline `code` spans that look like repo files or directories."""
    spans = _INLINE.findall(_FENCE.sub("", text))
    return {
        s for s in spans
        if not s.startswith(("/", "-", "~", "http")) and ("/" in s or s.endswith(_FILE_SUFFIXES))
    }


def test_runbooks_exist() -> None:
    assert RUNBOOKS, "runbooks/ is empty"


@pytest.mark.parametrize("path", RUNBOOKS, ids=lambda p: p.name)
def test_runbook_has_when_and_last_verified(path: Path) -> None:
    text = path.read_text()
    assert text.startswith("# "), f"{path.name}: missing title"
    assert "**When:**" in text, f"{path.name}: missing **When:** line"
    assert re.search(r"\*\*Last verified:\*\* \d{4}-\d{2}-\d{2}", text), (
        f"{path.name}: missing **Last verified:** YYYY-MM-DD"
    )


@pytest.mark.parametrize("path", RUNBOOKS, ids=lambda p: p.name)
def test_runbook_is_listed_in_agents_md(path: Path) -> None:
    agents = (ROOT / "AGENTS.md").read_text()
    assert f"runbooks/{path.name}" in agents, f"add runbooks/{path.name} to the table in AGENTS.md"


@pytest.mark.parametrize("path", RUNBOOKS, ids=lambda p: p.name)
def test_runbook_paths_exist(path: Path) -> None:
    missing = [
        p for p in sorted(_mentioned_paths(path.read_text()))
        if not (ROOT / p).exists() and not (ROOT / "runbooks" / p).exists()
    ]
    assert not missing, f"{path.name} mentions paths that don't exist: {missing}"
