"""Tests for the $souls quote cog — data file integrity and the loader's guards."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from cogs.souls_cog.main import (
    GAMES,
    build_quote_view,
    format_quote,
    load_quotes,
)


def test_shipped_quotes_cover_every_game_with_unique_lines() -> None:
    quotes = load_quotes()
    assert {q.game for q in quotes} == GAMES.keys()
    texts = [q.text for q in quotes]
    assert len(texts) == len(set(texts)), "duplicate quote text"


def test_every_shipped_quote_renders_within_text_limit() -> None:
    for quote in load_quotes():
        view = build_quote_view(quote)
        assert view.content_length() <= 4000


def test_multiline_quote_formats_every_line_as_closed_italic_heading() -> None:
    assert format_quote("Leave us be.\nAs thy kind always have.") == (
        "### *“Leave us be.*\n### *As thy kind always have.”*"
    )
    assert format_quote("Hesitation is defeat.") == "### *“Hesitation is defeat.”*"


def _write(tmp_path: Path, data: object) -> Path:
    path = tmp_path / "quotes.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _entry(**overrides: str) -> dict[str, str]:
    return {"speaker": "X", "text": "Y", "source_url": "https://example.com"} | overrides


def test_loader_rejects_unknown_or_missing_game(tmp_path: Path) -> None:
    good = {key: [_entry(text=key)] for key in GAMES}
    with pytest.raises(ValueError):
        load_quotes(_write(tmp_path, good | {"elden": [_entry()]}))
    with pytest.raises(ValueError):
        load_quotes(_write(tmp_path, {k: v for k, v in good.items() if k != "bb"}))


@pytest.mark.parametrize("bad", [{"speaker": " "}, {"text": ""}, {"source_url": "wiki"}])
def test_loader_rejects_incomplete_entry(tmp_path: Path, bad: dict[str, str]) -> None:
    data = {key: [_entry(text=key)] for key in GAMES}
    data["ds3"] = [_entry(**bad)]
    with pytest.raises(ValueError):
        load_quotes(_write(tmp_path, data))


def test_loader_rejects_empty_game(tmp_path: Path) -> None:
    data = {key: [_entry(text=key)] for key in GAMES} | {"sekiro": []}
    with pytest.raises(ValueError):
        load_quotes(_write(tmp_path, data))
