"""Bilingual fact catalog and transaction-safe, per-channel shuffle cycles."""

import json
from dataclasses import dataclass
from pathlib import Path

from db import DatabaseMixin


@dataclass(frozen=True, slots=True)
class FunFact:
    """One sourced fact expressed in Spanish and English."""

    id: str
    es: str
    en: str
    source_name: str
    source_url: str


class FactsMixin(DatabaseMixin):
    """Store the fact catalog and draw without repeats until a cycle ends."""

    async def seed_facts(self) -> None:
        """Upsert bundled facts without resetting any channel's progress."""
        directory = Path(__file__).resolve().parent.parent / "cogs/dyi_cog/data"
        facts = [
            FunFact(**item)
            for path in sorted(directory.glob("*.json"))
            for item in json.loads(path.read_text(encoding="utf-8"))
        ]
        if not facts:
            raise ValueError("The bundled fact catalog is empty")
        async with self._pool().acquire() as conn, conn.transaction():
            await conn.executemany(
                """
                INSERT INTO fun_facts (id, es, en, source_name, source_url)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (id) DO UPDATE SET
                    es = EXCLUDED.es, en = EXCLUDED.en,
                    source_name = EXCLUDED.source_name,
                    source_url = EXCLUDED.source_url
                """,
                [(f.id, f.es, f.en, f.source_name, f.source_url) for f in facts],
            )

    async def next_fact(self, channel_id: int) -> FunFact:
        """Reserve a random unseen fact, surviving restarts and concurrent calls.

        The channel row lock serializes draws across bot processes. At the
        cycle boundary, exclude the previous draw to prevent back-to-back
        repeats unless the catalog contains just one fact. A reserved fact
        counts as used even if its subsequent Discord delivery fails.
        """
        async with self._pool().acquire() as conn, conn.transaction():
            await conn.execute(
                "INSERT INTO fact_cycles (channel_id) VALUES ($1) "
                "ON CONFLICT (channel_id) DO NOTHING",
                channel_id,
            )
            await conn.fetchval(
                "SELECT channel_id FROM fact_cycles WHERE channel_id = $1 FOR UPDATE",
                channel_id,
            )
            row = await conn.fetchrow(
                """
                SELECT f.* FROM fun_facts f
                WHERE NOT EXISTS (
                    SELECT 1 FROM fact_seen s
                    WHERE s.channel_id = $1 AND s.fact_id = f.id
                )
                ORDER BY random() LIMIT 1
                """,
                channel_id,
            )
            if row is None:
                row = await conn.fetchrow(
                    """
                    SELECT f.* FROM fun_facts f
                    WHERE f.id IS DISTINCT FROM (
                        SELECT last_fact_id FROM fact_cycles WHERE channel_id = $1
                    ) OR (SELECT count(*) FROM fun_facts) = 1
                    ORDER BY random() LIMIT 1
                    """,
                    channel_id,
                )
                if row is None:
                    raise LookupError("The fact catalog is empty")
                await conn.execute("DELETE FROM fact_seen WHERE channel_id = $1", channel_id)
            fact = FunFact(**dict(row))
            await conn.execute(
                "INSERT INTO fact_seen (channel_id, fact_id) VALUES ($1, $2)",
                channel_id, fact.id,
            )
            await conn.execute(
                "UPDATE fact_cycles SET last_fact_id = $2 WHERE channel_id = $1",
                channel_id, fact.id,
            )
            return fact
