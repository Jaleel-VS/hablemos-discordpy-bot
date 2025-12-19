import asyncpg
import os
import logging
from typing import Optional

class Database:
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
        self.database_url = os.getenv('DATABASE_URL')

        if not self.database_url:
            raise ValueError("DATABASE_URL not found in environment variables")

    async def connect(self):
        """Create a connection pool to the database"""
        try:
            self.pool = await asyncpg.create_pool(
                self.database_url,
                min_size=1,
                max_size=10,
                command_timeout=60
            )
            logging.info("Database connection pool created successfully")
            await self.initialize_schema()
        except Exception as e:
            logging.error(f"Failed to connect to database: {e}")
            raise

    async def close(self):
        """Close the database connection pool"""
        if self.pool:
            await self.pool.close()
            logging.info("Database connection pool closed")

    async def initialize_schema(self):
        """Initialize database tables if they don't exist"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            # Notes table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS notes (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    username VARCHAR(255) NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Introductions tracking table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS introductions (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id)
                )
            ''')

            # Feature settings table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS feature_settings (
                    feature_name VARCHAR(100) PRIMARY KEY,
                    enabled BOOLEAN NOT NULL DEFAULT FALSE
                )
            ''')

            # Initialize intro tracker as disabled by default
            await conn.execute('''
                INSERT INTO feature_settings (feature_name, enabled)
                VALUES ('intro_tracker', FALSE)
                ON CONFLICT (feature_name) DO NOTHING
            ''')

            logging.info("Database schema initialized")

    async def add_note(self, user_id: int, username: str, content: str) -> int:
        """Add a new note to the database"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                'INSERT INTO notes (user_id, username, content) VALUES ($1, $2, $3) RETURNING id',
                user_id, username, content
            )
            return row['id']

    async def get_note(self, note_id: int) -> Optional[dict]:
        """Get a note by its ID"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT id, user_id, username, content, created_at FROM notes WHERE id = $1',
                note_id
            )
            if row:
                return dict(row)
            return None

    async def get_user_notes(self, user_id: int, limit: int = 10) -> list[dict]:
        """Get all notes for a specific user"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                'SELECT id, user_id, username, content, created_at FROM notes WHERE user_id = $1 ORDER BY created_at DESC LIMIT $2',
                user_id, limit
            )
            return [dict(row) for row in rows]

    async def delete_note(self, note_id: int, user_id: int) -> bool:
        """Delete a note (only if it belongs to the user)"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                'DELETE FROM notes WHERE id = $1 AND user_id = $2',
                note_id, user_id
            )
            return result == 'DELETE 1'

    # Introduction Tracking Methods

    async def check_user_introduction(self, user_id: int) -> Optional[dict]:
        """Check if user has posted an introduction in the last 30 days"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow('''
                SELECT id, user_id, posted_at
                FROM introductions
                WHERE user_id = $1
                AND posted_at > NOW() - INTERVAL '30 days'
            ''', user_id)
            if row:
                return dict(row)
            return None

    async def record_introduction(self, user_id: int) -> bool:
        """Record a user's introduction. Returns True if successful, False if already exists"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            try:
                await conn.execute('''
                    INSERT INTO introductions (user_id, posted_at)
                    VALUES ($1, NOW())
                    ON CONFLICT (user_id) DO UPDATE
                    SET posted_at = NOW()
                ''', user_id)
                return True
            except Exception as e:
                logging.error(f"Error recording introduction: {e}")
                return False

    async def get_feature_setting(self, feature_name: str) -> bool:
        """Get whether a feature is enabled"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT enabled FROM feature_settings WHERE feature_name = $1',
                feature_name
            )
            if row:
                return row['enabled']
            return False

    async def set_feature_setting(self, feature_name: str, enabled: bool) -> bool:
        """Set whether a feature is enabled"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO feature_settings (feature_name, enabled)
                VALUES ($1, $2)
                ON CONFLICT (feature_name) DO UPDATE
                SET enabled = $2
            ''', feature_name, enabled)
            return True
