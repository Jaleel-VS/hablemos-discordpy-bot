"""Database mixin for members' saved world clocks ($clock)."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

import asyncpg

from db import DatabaseMixin

logger = logging.getLogger(__name__)

# Serializes one member's writes so the clock limit holds under concurrent adds.
_LOCK = "SELECT pg_advisory_xact_lock(hashtextextended('world_clock:' || $1::bigint::text, 0))"


@dataclass(frozen=True)
class SavedClock:
    """One saved clock: a member's label and a zone key (see worldclock_cog.zones)."""

    label: str
    zone: str


class SaveClockResult(Enum):
    """Outcome of adding or editing a clock."""

    ADDED = "added"
    REPLACED = "replaced"
    LIMIT_REACHED = "limit_reached"
    NOT_FOUND = "not_found"
    NAME_TAKEN = "name_taken"


class WorldClockMixin(DatabaseMixin):
    """Queries for the ``user_world_clocks`` table."""

    async def get_world_clocks(self, user_id: int) -> list[SavedClock]:
        """A member's clocks in the order they were added."""
        rows = await self._fetch(
            "SELECT label, zone FROM user_world_clocks WHERE user_id = $1 ORDER BY created_at",
            user_id,
        )
        return [SavedClock(row["label"], row["zone"]) for row in rows]

    async def add_world_clock(
        self, user_id: int, label: str, zone: str, limit: int
    ) -> SaveClockResult:
        """Add a clock, or change the zone of the one with the same label.

        Changing an existing clock works at the limit; only new labels count.
        """
        async with self._pool().acquire() as conn, conn.transaction():
            await conn.execute(_LOCK, user_id)
            updated = await conn.execute(
                "UPDATE user_world_clocks SET label = $2, zone = $3 "
                "WHERE user_id = $1 AND lower(label) = lower($2)",
                user_id, label, zone,
            )
            if updated != "UPDATE 0":
                return SaveClockResult.REPLACED
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM user_world_clocks WHERE user_id = $1", user_id
            )
            if count >= limit:
                return SaveClockResult.LIMIT_REACHED
            await conn.execute(
                "INSERT INTO user_world_clocks (user_id, label, zone) VALUES ($1, $2, $3)",
                user_id, label, zone,
            )
            return SaveClockResult.ADDED

    async def edit_world_clock(
        self, user_id: int, old_label: str, label: str, zone: str
    ) -> SaveClockResult:
        """Rename and re-zone an existing clock, keeping its place in the order."""
        async with self._pool().acquire() as conn, conn.transaction():
            await conn.execute(_LOCK, user_id)
            try:
                updated = await conn.execute(
                    "UPDATE user_world_clocks SET label = $3, zone = $4 "
                    "WHERE user_id = $1 AND lower(label) = lower($2)",
                    user_id, old_label, label, zone,
                )
            except asyncpg.UniqueViolationError:
                return SaveClockResult.NAME_TAKEN
            if updated == "UPDATE 0":
                return SaveClockResult.NOT_FOUND
            return SaveClockResult.REPLACED

    async def remove_world_clock(self, user_id: int, label: str) -> bool:
        """Delete a clock by label (case-insensitive). True if one was removed."""
        status = await self._execute(
            "DELETE FROM user_world_clocks WHERE user_id = $1 AND lower(label) = lower($2)",
            user_id, label,
        )
        return status != "DELETE 0"

    async def clear_world_clocks(self, user_id: int) -> int:
        """Delete all of a member's clocks; returns how many were removed."""
        status = await self._execute(
            "DELETE FROM user_world_clocks WHERE user_id = $1", user_id
        )
        return int(status.rsplit(" ", 1)[-1])
