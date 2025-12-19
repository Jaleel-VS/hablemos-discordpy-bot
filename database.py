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
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS notes (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    username VARCHAR(255) NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
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
