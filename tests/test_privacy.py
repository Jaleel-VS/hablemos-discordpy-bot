"""$deletemydata must cover every per-user table in the schema."""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from cogs.privacy_cog.views import ConfirmDeleteDataView
from db.privacy import DELETED_TABLES, KEPT_TABLES, _rowcount

ROOT = Path(__file__).resolve().parent.parent
SCHEMAS = [ROOT / "db" / "schema.py", ROOT / "activity" / "backend" / "app" / "db.py"]

# Columns that hold the ID of the member the row is about.
_USER_COLUMN = re.compile(r"^\s*(user_id|user_a|user_b|solved_by)\s", re.MULTILINE)
_TABLE = re.compile(r"CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\n\s*\)", re.DOTALL)


def _user_tables() -> set[str]:
    tables: set[str] = set()
    for path in SCHEMAS:
        for name, body in _TABLE.findall(path.read_text()):
            if _USER_COLUMN.search(body):
                tables.add(name)
    return tables


def test_schema_scan_finds_user_tables() -> None:
    # Guards the regex itself: if it stops matching, the coverage test passes vacuously.
    assert {"notes", "leaderboard_users", "game_results", "spotify_optins"} <= _user_tables()


def test_every_user_table_is_deleted_or_kept() -> None:
    missing = _user_tables() - DELETED_TABLES - set(KEPT_TABLES)
    assert not missing, (
        f"Per-user tables not handled by $deletemydata: {sorted(missing)}. "
        "Add them to db/privacy.py (_DELETES, _ANONYMIZE, or KEPT_TABLES)."
    )


def test_no_table_is_both_deleted_and_kept() -> None:
    # leaderboard_users is deliberately in both _DELETES and _ANONYMIZE
    # (deleted unless banned), but never in KEPT_TABLES.
    assert not DELETED_TABLES & set(KEPT_TABLES)


@pytest.mark.parametrize(
    ("status", "expected"),
    [("DELETE 3", 3), ("UPDATE 0", 0), ("INSERT 0 1", 1), ("SELECT", 0)],
)
def test_rowcount(status: str, expected: int) -> None:
    assert _rowcount(status) == expected


@pytest.mark.asyncio
async def test_confirm_deletes_and_notifies_cogs() -> None:
    bot = SimpleNamespace(
        db=SimpleNamespace(delete_user_data=AsyncMock(return_value=7)),
        dispatch=MagicMock(),
    )
    view = ConfirmDeleteDataView(cast(Any, bot), requester_id=1, target_id=42)
    interaction = MagicMock()
    interaction.response.edit_message = AsyncMock()

    await view.confirm.callback(interaction)

    bot.db.delete_user_data.assert_awaited_once_with(42)
    bot.dispatch.assert_called_once_with("user_data_deleted", 42)
    assert "Deleted 7" in interaction.response.edit_message.await_args.kwargs["embed"].description
    assert all(item.disabled for item in view.children)


@pytest.mark.asyncio
async def test_failed_deletion_does_not_notify_cogs() -> None:
    bot = SimpleNamespace(
        db=SimpleNamespace(delete_user_data=AsyncMock(side_effect=RuntimeError("db down"))),
        dispatch=MagicMock(),
    )
    view = ConfirmDeleteDataView(cast(Any, bot), requester_id=1, target_id=42)
    interaction = MagicMock()
    interaction.response.edit_message = AsyncMock()

    await view.confirm.callback(interaction)

    bot.dispatch.assert_not_called()
    assert "nothing was deleted" in interaction.response.edit_message.await_args.kwargs["embed"].description
