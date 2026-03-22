import logging

import asyncpg

logger = logging.getLogger(__name__)

class DatabaseMixin:
    """Base mixin providing pool access helpers."""
    pool: asyncpg.Pool | None

    def _pool(self) -> asyncpg.Pool:
        """Return an initialized connection pool."""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        return self.pool

    async def _fetchrow(self, query: str, *args):
        async with self._pool().acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def _fetchval(self, query: str, *args):
        async with self._pool().acquire() as conn:
            return await conn.fetchval(query, *args)

    async def _fetch(self, query: str, *args) -> list:
        async with self._pool().acquire() as conn:
            return await conn.fetch(query, *args)

    async def _execute(self, query: str, *args) -> str:
        async with self._pool().acquire() as conn:
            return await conn.execute(query, *args)

from db.notes import NotesMixin
from db.introductions import IntroductionsMixin
from db.settings import SettingsMixin
from db.conversations import ConversationsMixin
from db.vocab import VocabMixin
from db.leaderboard import LeaderboardMixin
from db.quotes import QuotesMixin
from db.practice import PracticeMixin
from db.metrics import MetricsMixin
from db.schema import initialize_schema

class Database(
    NotesMixin,
    IntroductionsMixin,
    SettingsMixin,
    ConversationsMixin,
    VocabMixin,
    LeaderboardMixin,
    QuotesMixin,
    PracticeMixin,
    MetricsMixin,
):
    def __init__(self, database_url: str):
        self.pool: asyncpg.Pool | None = None
        self.database_url = database_url

    async def connect(self):
        """Create a connection pool to the database"""
        try:
            self.pool = await asyncpg.create_pool(
                self.database_url,
                min_size=1,
                max_size=10,
                command_timeout=60,
                statement_cache_size=0,
            )
            logger.info("Database connection pool created successfully")
            await initialize_schema(self.pool)
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    async def close(self):
        """Close the database connection pool"""
        if self.pool:
            await self.pool.close()
            logger.info("Database connection pool closed")
