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

            # Conversations table for language learning
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS conversations (
                    id SERIAL PRIMARY KEY,
                    language VARCHAR(10) NOT NULL,
                    level VARCHAR(20) NOT NULL,
                    category VARCHAR(50) NOT NULL,
                    scenario_intro TEXT NOT NULL,
                    speaker1_name VARCHAR(100) NOT NULL,
                    speaker2_name VARCHAR(100) NOT NULL,
                    conversation_text TEXT NOT NULL,
                    usage_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_used_at TIMESTAMP
                )
            ''')

            # Index for conversation lookups
            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_conversation_lookup
                ON conversations(language, level, category, usage_count)
            ''')

            # User conversation daily limits table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS user_conversation_limits (
                    user_id BIGINT PRIMARY KEY,
                    date DATE DEFAULT CURRENT_DATE,
                    conversation_count INTEGER DEFAULT 0
                )
            ''')

            # Index for daily limit lookups
            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_user_limits_date
                ON user_conversation_limits(user_id, date)
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

    # Conversation Learning Methods

    async def add_conversation(self, language: str, level: str, category: str,
                              scenario_intro: str, speaker1_name: str,
                              speaker2_name: str, conversation_text: str) -> int:
        """Add a generated conversation to the database"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow('''
                INSERT INTO conversations
                (language, level, category, scenario_intro, speaker1_name,
                 speaker2_name, conversation_text)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING id
            ''', language, level, category, scenario_intro, speaker1_name,
                 speaker2_name, conversation_text)
            return row['id']

    async def get_random_conversation(self, language: str, level: str,
                                      category: str) -> Optional[dict]:
        """Get a random conversation, preferring less-used ones"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            # Get conversation with lowest usage count (random among ties)
            row = await conn.fetchrow('''
                SELECT id, language, level, category, scenario_intro,
                       speaker1_name, speaker2_name, conversation_text, usage_count
                FROM conversations
                WHERE language = $1 AND level = $2 AND category = $3
                ORDER BY usage_count ASC, RANDOM()
                LIMIT 1
            ''', language, level, category)

            if row:
                return dict(row)
            return None

    async def increment_conversation_usage(self, conversation_id: int) -> None:
        """Increment usage count and update last_used_at"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            await conn.execute('''
                UPDATE conversations
                SET usage_count = usage_count + 1,
                    last_used_at = NOW()
                WHERE id = $1
            ''', conversation_id)

    async def check_regeneration_needed(self, language: str, level: str,
                                       category: str) -> bool:
        """Check if all conversations in a combo have been used at least once"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            result = await conn.fetchrow('''
                SELECT
                    COUNT(*) as total,
                    MIN(usage_count) as min_usage
                FROM conversations
                WHERE language = $1 AND level = $2 AND category = $3
            ''', language, level, category)

            if not result or result['total'] == 0:
                return False  # No conversations exist, don't regenerate

            # If min usage > 0, all have been used at least once
            return result['min_usage'] > 0

    async def get_conversation_count(self, language: str = None, level: str = None,
                                    category: str = None) -> int:
        """Get count of conversations matching criteria"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            if language and level and category:
                count = await conn.fetchval('''
                    SELECT COUNT(*) FROM conversations
                    WHERE language = $1 AND level = $2 AND category = $3
                ''', language, level, category)
            else:
                count = await conn.fetchval('SELECT COUNT(*) FROM conversations')
            return count or 0

    async def delete_old_conversations(self, language: str, level: str,
                                      category: str) -> int:
        """Delete old conversations for a specific combo (for regeneration)"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            result = await conn.execute('''
                DELETE FROM conversations
                WHERE language = $1 AND level = $2 AND category = $3
            ''', language, level, category)
            # Extract count from result like "DELETE 10"
            return int(result.split()[-1]) if result and result.split() else 0

    # Daily Conversation Limit Methods

    async def check_daily_limit(self, user_id: int, limit: int = 2) -> int:
        """
        Check how many conversations a user has requested today

        Args:
            user_id: Discord user ID
            limit: Daily limit (default: 2)

        Returns:
            Number of conversations used today
        """
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow('''
                SELECT conversation_count
                FROM user_conversation_limits
                WHERE user_id = $1 AND date = CURRENT_DATE
            ''', user_id)

            if row:
                return row['conversation_count']
            return 0

    async def increment_daily_usage(self, user_id: int) -> None:
        """
        Increment a user's daily conversation count

        Creates a new entry if user hasn't requested any today,
        or increments existing count for today.
        """
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO user_conversation_limits (user_id, date, conversation_count)
                VALUES ($1, CURRENT_DATE, 1)
                ON CONFLICT (user_id) DO UPDATE
                SET conversation_count = CASE
                    WHEN user_conversation_limits.date = CURRENT_DATE
                    THEN user_conversation_limits.conversation_count + 1
                    ELSE 1
                    END,
                    date = CURRENT_DATE
            ''', user_id)

    async def get_daily_usage_remaining(self, user_id: int, limit: int = 2) -> int:
        """
        Get how many conversations a user has remaining today

        Args:
            user_id: Discord user ID
            limit: Daily limit (default: 2)

        Returns:
            Number of conversations remaining (0 if limit reached)
        """
        used = await self.check_daily_limit(user_id, limit)
        remaining = max(0, limit - used)
        return remaining
