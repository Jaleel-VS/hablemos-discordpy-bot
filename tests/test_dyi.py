"""Catalog guarantees and real-Postgres tests for persistent fact cycles.

Set TEST_DATABASE_URL to a disposable local Postgres with CREATEDB permission.
Each database test creates and drops its own temporary database.
"""

import asyncio
import json
import os
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest

from db import Database
from db.schema import initialize_schema

DATA_DIR = Path(__file__).resolve().parents[1] / "cogs/dyi_cog/data"
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")


def test_bilingual_catalog() -> None:
    """Ship at least 500 distinct, attributed facts that fit a Discord card."""
    facts = [
        fact
        for path in sorted(DATA_DIR.glob("*.json"))
        for fact in json.loads(path.read_text(encoding="utf-8"))
    ]
    assert len(facts) >= 500
    for key in ("id", "es", "en"):
        assert len({f[key].strip().casefold() for f in facts}) == len(facts)
    for fact in facts:
        assert set(fact) == {"id", "es", "en", "source_name", "source_url"}
        assert all(isinstance(value, str) and value.strip() for value in fact.values())
        assert fact["es"] != fact["en"]
        assert fact["source_url"].startswith("https://")
        assert sum(len(value) for value in fact.values()) < 3500


@pytest.fixture
async def fact_db() -> AsyncIterator[tuple[Database, str]]:
    """Use a separate database because legacy migrations assume one schema."""
    if not TEST_DATABASE_URL:
        pytest.skip("set TEST_DATABASE_URL to run fact cycle integration tests")
    db_name = "dyi_test_" + uuid4().hex
    admin = await asyncpg.connect(TEST_DATABASE_URL)
    database = Database(TEST_DATABASE_URL)
    await admin.execute(f'CREATE DATABASE "{db_name}"')
    try:
        database.pool = await asyncpg.create_pool(
            TEST_DATABASE_URL, min_size=1, max_size=10,
            database=db_name,
        )
        await initialize_schema(database._pool())
        yield database, db_name
    finally:
        await database.close()
        await admin.execute(f'DROP DATABASE "{db_name}"')
        await admin.close()


async def _insert_facts(database: Database, count: int) -> set[str]:
    ids = {f"fact-{n}" for n in range(count)}
    async with database._pool().acquire() as conn:
        await conn.executemany(
            "INSERT INTO fun_facts VALUES ($1, $2, $3, $4, $5)",
            [(key, f"Dato {key}", f"Fact {key}", "NASA", "https://science.nasa.gov/") for key in sorted(ids)],
        )
    return ids


async def test_concurrent_draws_complete_each_cycle(fact_db: tuple[Database, str]) -> None:
    """Competing draws cannot repeat or lose a fact within either cycle."""
    database, _ = fact_db
    expected = await _insert_facts(database, 12)
    for _ in range(2):
        draws = await asyncio.gather(*(database.next_fact(100) for _ in expected))
        assert {fact.id for fact in draws} == expected
        assert await database._fetchval("SELECT count(*) FROM fact_seen WHERE channel_id = 100") == 12


async def test_cycle_boundary_and_channel_independence(fact_db: tuple[Database, str]) -> None:
    """No adjacent repeat at rollover; another channel has its own whole deck."""
    database, _ = fact_db
    expected = await _insert_facts(database, 3)
    first_cycle = [await database.next_fact(100) for _ in expected]
    second_cycle = [await database.next_fact(100) for _ in expected]
    other_channel = [await database.next_fact(200) for _ in expected]
    assert {fact.id for fact in first_cycle} == expected
    assert {fact.id for fact in second_cycle} == expected
    assert first_cycle[-1].id != second_cycle[0].id
    assert {fact.id for fact in other_channel} == expected


async def test_restart_and_reseed_preserve_progress(fact_db: tuple[Database, str]) -> None:
    """Loading the bundled catalog again does not reset a partly-used deck."""
    database, db_name = fact_db
    await database.seed_facts()
    count = await database._fetchval("SELECT count(*) FROM fun_facts")
    assert count >= 500
    first = await database.next_fact(100)
    await database.close()
    restarted = Database(TEST_DATABASE_URL)
    restarted.pool = await asyncpg.create_pool(
        TEST_DATABASE_URL, min_size=1, max_size=2,
        database=db_name,
    )
    try:
        await restarted.seed_facts()
        assert await restarted._fetchval("SELECT count(*) FROM fun_facts") == count
        remaining = [await restarted.next_fact(100) for _ in range(count - 1)]
        assert first.id not in {fact.id for fact in remaining}
        assert len({fact.id for fact in remaining}) == count - 1
        after_rollover = await restarted.next_fact(100)
        assert after_rollover.id != remaining[-1].id
    finally:
        await restarted.close()


async def test_empty_singleton_and_catalog_growth(fact_db: tuple[Database, str]) -> None:
    """Empty catalogs fail explicitly; singleton cycles and new facts work."""
    database, _ = fact_db
    with pytest.raises(LookupError):
        await database.next_fact(100)
    assert await database._fetchval("SELECT count(*) FROM fact_cycles") == 0
    await _insert_facts(database, 1)
    assert (await database.next_fact(100)).id == "fact-0"
    assert (await database.next_fact(100)).id == "fact-0"
    await database._execute(
        "INSERT INTO fun_facts VALUES ('new', 'Nuevo dato', 'New fact', 'NASA', 'https://science.nasa.gov/')"
    )
    assert (await database.next_fact(100)).id == "new"
