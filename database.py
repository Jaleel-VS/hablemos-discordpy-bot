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
                command_timeout=60,
                statement_cache_size=0  # Disable statement cache to avoid schema change issues
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

            # Introductions tracking table (stores every attempt, no unique constraint)
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS introductions (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Migration: drop old unique constraint if it exists
            await conn.execute('''
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM pg_constraint
                        WHERE conname = 'introductions_user_id_key'
                    ) THEN
                        ALTER TABLE introductions DROP CONSTRAINT introductions_user_id_key;
                    END IF;
                END $$;
            ''')

            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_introductions_user_id
                ON introductions(user_id)
            ''')

            # Bot settings table (general key-value store for channel IDs, etc.)
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS bot_settings (
                    setting_key VARCHAR(100) PRIMARY KEY,
                    setting_value BIGINT NOT NULL
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

            # Vocabulary notes table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS vocab_notes (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    username VARCHAR(255) NOT NULL,
                    word VARCHAR(500) NOT NULL,
                    translation TEXT,
                    language VARCHAR(50),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Index for vocab note lookups
            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_vocab_user_id
                ON vocab_notes(user_id)
            ''')

            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_vocab_word
                ON vocab_notes(user_id, word)
            ''')

            # Leaderboard users table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS leaderboard_users (
                    user_id BIGINT PRIMARY KEY,
                    username VARCHAR(255) NOT NULL,
                    opted_in BOOLEAN DEFAULT TRUE,
                    banned BOOLEAN DEFAULT FALSE,
                    learning_spanish BOOLEAN DEFAULT FALSE,
                    learning_english BOOLEAN DEFAULT FALSE,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_leaderboard_active
                ON leaderboard_users(opted_in, banned)
            ''')

            # Leaderboard activity table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS leaderboard_activity (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    activity_type VARCHAR(50) NOT NULL DEFAULT 'message',
                    channel_id BIGINT,
                    points INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES leaderboard_users(user_id) ON DELETE CASCADE
                )
            ''')

            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_activity_user_date
                ON leaderboard_activity(user_id, created_at)
            ''')

            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_activity_date
                ON leaderboard_activity(created_at)
            ''')

            # Add round_id column to leaderboard_activity if it doesn't exist
            await conn.execute('''
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='leaderboard_activity' AND column_name='round_id'
                    ) THEN
                        ALTER TABLE leaderboard_activity ADD COLUMN round_id INTEGER;
                    END IF;
                END $$;
            ''')

            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_activity_round
                ON leaderboard_activity(round_id)
            ''')

            # Add message_id column to leaderboard_activity if it doesn't exist
            await conn.execute('''
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='leaderboard_activity' AND column_name='message_id'
                    ) THEN
                        ALTER TABLE leaderboard_activity ADD COLUMN message_id BIGINT;
                    END IF;
                END $$;
            ''')

            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_activity_message
                ON leaderboard_activity(message_id)
            ''')

            # Leaderboard excluded channels table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS leaderboard_excluded_channels (
                    channel_id BIGINT PRIMARY KEY,
                    channel_name VARCHAR(255),
                    added_by BIGINT NOT NULL,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # League rounds table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS league_rounds (
                    round_id SERIAL PRIMARY KEY,
                    round_number INTEGER NOT NULL,
                    start_date TIMESTAMPTZ NOT NULL,
                    end_date TIMESTAMPTZ NOT NULL,
                    status VARCHAR(20) DEFAULT 'active',
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_league_rounds_status
                ON league_rounds(status)
            ''')

            # League round winners table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS league_round_winners (
                    id SERIAL PRIMARY KEY,
                    round_id INTEGER NOT NULL,
                    user_id BIGINT NOT NULL,
                    username VARCHAR(255) NOT NULL,
                    league_type VARCHAR(20) NOT NULL,
                    rank INTEGER NOT NULL,
                    total_score INTEGER NOT NULL,
                    active_days INTEGER NOT NULL,
                    received_role BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (round_id) REFERENCES league_rounds(round_id) ON DELETE CASCADE
                )
            ''')

            # Add received_role column if it doesn't exist (migration for existing DBs)
            await conn.execute('''
                ALTER TABLE league_round_winners
                ADD COLUMN IF NOT EXISTS received_role BOOLEAN DEFAULT FALSE
            ''')

            # Separate table to track champion role recipients (decoupled from winners)
            # This handles cases where role goes to rank 4+ due to cooldown
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS league_role_recipients (
                    id SERIAL PRIMARY KEY,
                    round_id INTEGER NOT NULL,
                    user_id BIGINT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (round_id) REFERENCES league_rounds(round_id) ON DELETE CASCADE,
                    UNIQUE(round_id, user_id)
                )
            ''')

            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_league_winners_user
                ON league_round_winners(user_id, rank)
            ''')

            # Practice cards table (global card pool for SRS practice)
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS practice_cards (
                    id SERIAL PRIMARY KEY,
                    word VARCHAR(500) NOT NULL,
                    translation TEXT NOT NULL,
                    language VARCHAR(50) NOT NULL,
                    sentence TEXT NOT NULL,
                    sentence_with_blank TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(word, language)
                )
            ''')

            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_practice_language
                ON practice_cards(language)
            ''')

            # User card progress table (per-user SRS tracking)
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS user_card_progress (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    card_id INTEGER NOT NULL REFERENCES practice_cards(id) ON DELETE CASCADE,
                    last_review TIMESTAMPTZ,
                    next_review TIMESTAMPTZ,
                    interval_days REAL DEFAULT 1.0,
                    ease_factor REAL DEFAULT 2.5,
                    repetitions INTEGER DEFAULT 0,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(user_id, card_id)
                )
            ''')

            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_progress_user
                ON user_card_progress(user_id)
            ''')

            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_progress_due
                ON user_card_progress(user_id, next_review)
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
        """Check if user has posted an introduction in the last 90 days"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow('''
                SELECT id, user_id, posted_at
                FROM introductions
                WHERE user_id = $1
                AND posted_at > NOW() - INTERVAL '90 days'
                ORDER BY posted_at DESC
                LIMIT 1
            ''', user_id)
            if row:
                return dict(row)
            return None

    async def get_introduction_count(self, user_id: int) -> int:
        """Get total number of introductions a user has posted"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            count = await conn.fetchval('''
                SELECT COUNT(*) FROM introductions WHERE user_id = $1
            ''', user_id)
            return count or 0

    async def record_introduction(self, user_id: int) -> bool:
        """Record a user's introduction attempt"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            try:
                await conn.execute('''
                    INSERT INTO introductions (user_id, posted_at)
                    VALUES ($1, NOW())
                ''', user_id)
                return True
            except Exception as e:
                logging.error(f"Error recording introduction: {e}")
                return False

    # Bot Settings Methods

    async def get_bot_setting(self, setting_key: str) -> Optional[int]:
        """Get a bot setting value by key"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT setting_value FROM bot_settings WHERE setting_key = $1',
                setting_key
            )
            return row['setting_value'] if row else None

    async def set_bot_setting(self, setting_key: str, setting_value: int) -> bool:
        """Set a bot setting value (upsert)"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO bot_settings (setting_key, setting_value)
                VALUES ($1, $2)
                ON CONFLICT (setting_key) DO UPDATE
                SET setting_value = $2
            ''', setting_key, setting_value)
            return True

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

    # Vocabulary Notes Methods

    async def add_vocab_note(self, user_id: int, username: str, word: str,
                            translation: Optional[str] = None,
                            language: Optional[str] = None) -> int:
        """Add a new vocabulary note to the database"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow('''
                INSERT INTO vocab_notes (user_id, username, word, translation, language)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
            ''', user_id, username, word, translation, language)
            return row['id']

    async def get_user_vocab_notes(self, user_id: int, limit: int = 50) -> list[dict]:
        """Get all vocab notes for a specific user"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT id, user_id, username, word, translation, language, created_at
                FROM vocab_notes
                WHERE user_id = $1
                ORDER BY created_at DESC
                LIMIT $2
            ''', user_id, limit)
            return [dict(row) for row in rows]

    async def search_vocab_notes(self, user_id: int, search_term: str,
                                 limit: int = 20) -> list[dict]:
        """Search vocab notes by word or translation"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            search_pattern = f'%{search_term}%'
            rows = await conn.fetch('''
                SELECT id, user_id, username, word, translation, language, created_at
                FROM vocab_notes
                WHERE user_id = $1
                AND (word ILIKE $2 OR translation ILIKE $2)
                ORDER BY created_at DESC
                LIMIT $3
            ''', user_id, search_pattern, limit)
            return [dict(row) for row in rows]

    async def delete_vocab_note(self, note_id: int, user_id: int) -> bool:
        """Delete a vocab note (only if it belongs to the user)"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            result = await conn.execute('''
                DELETE FROM vocab_notes
                WHERE id = $1 AND user_id = $2
            ''', note_id, user_id)
            return result == 'DELETE 1'

    async def get_vocab_note_count(self, user_id: int) -> int:
        """Get total count of vocab notes for a user"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            count = await conn.fetchval('''
                SELECT COUNT(*) FROM vocab_notes WHERE user_id = $1
            ''', user_id)
            return count or 0

    # Leaderboard Methods

    async def leaderboard_join(self, user_id: int, username: str,
                              learning_spanish: bool, learning_english: bool) -> bool:
        """Add user to leaderboard system"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO leaderboard_users
                (user_id, username, opted_in, learning_spanish, learning_english)
                VALUES ($1, $2, TRUE, $3, $4)
                ON CONFLICT (user_id) DO UPDATE
                SET opted_in = TRUE,
                    learning_spanish = $3,
                    learning_english = $4,
                    username = $2,
                    updated_at = CURRENT_TIMESTAMP
            ''', user_id, username, learning_spanish, learning_english)
            return True

    async def leaderboard_leave(self, user_id: int) -> bool:
        """Remove user from leaderboard system"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            result = await conn.execute('''
                UPDATE leaderboard_users
                SET opted_in = FALSE,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = $1
            ''', user_id)
            return 'UPDATE' in result

    async def leaderboard_ban_user(self, user_id: int) -> bool:
        """Ban user from leaderboard"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            result = await conn.execute('''
                UPDATE leaderboard_users
                SET banned = TRUE,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = $1
            ''', user_id)
            return 'UPDATE' in result

    async def leaderboard_unban_user(self, user_id: int) -> bool:
        """Unban user from leaderboard"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            result = await conn.execute('''
                UPDATE leaderboard_users
                SET banned = FALSE,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = $1
            ''', user_id)
            return 'UPDATE' in result

    async def is_user_opted_in(self, user_id: int) -> bool:
        """Check if user is opted into leaderboard"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow('''
                SELECT opted_in FROM leaderboard_users
                WHERE user_id = $1
            ''', user_id)
            return row['opted_in'] if row else False

    async def is_user_banned(self, user_id: int) -> bool:
        """Check if user is banned from leaderboard"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow('''
                SELECT banned FROM leaderboard_users
                WHERE user_id = $1
            ''', user_id)
            return row['banned'] if row else False

    async def get_user_learning_languages(self, user_id: int) -> dict:
        """
        Get what languages a user is learning.

        Returns:
            {'learning_spanish': bool, 'learning_english': bool}
        """
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow('''
                SELECT learning_spanish, learning_english FROM leaderboard_users
                WHERE user_id = $1 AND opted_in = TRUE AND banned = FALSE
            ''', user_id)
            if row:
                return {
                    'learning_spanish': row['learning_spanish'],
                    'learning_english': row['learning_english']
                }
            return {'learning_spanish': False, 'learning_english': False}

    async def record_activity(self, user_id: int, activity_type: str = 'message',
                             channel_id: Optional[int] = None, points: int = 1,
                             round_id: Optional[int] = None, message_id: Optional[int] = None) -> None:
        """Record user activity for leaderboard"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO leaderboard_activity
                (user_id, activity_type, channel_id, points, round_id, message_id)
                VALUES ($1, $2, $3, $4, $5, $6)
            ''', user_id, activity_type, channel_id, points, round_id, message_id)

    async def get_daily_message_count(self, user_id: int) -> int:
        """Get count of messages recorded today for a user"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            count = await conn.fetchval('''
                SELECT COUNT(*)
                FROM leaderboard_activity
                WHERE user_id = $1
                AND activity_type = 'message'
                AND created_at >= CURRENT_DATE
            ''', user_id)
            return count or 0

    async def get_user_stats(self, user_id: int, round_id: Optional[int] = None) -> Optional[dict]:
        """Get leaderboard stats for a specific user in a specific round"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")

        # If no round_id specified, get current round
        if round_id is None:
            current_round = await self.get_current_round()
            if not current_round:
                return None
            round_id = current_round['round_id']

        async with self.pool.acquire() as conn:
            # Get user info
            user_row = await conn.fetchrow('''
                SELECT username, learning_spanish, learning_english
                FROM leaderboard_users
                WHERE user_id = $1 AND opted_in = TRUE AND banned = FALSE
            ''', user_id)

            if not user_row:
                return None

            # Get stats for this round
            stats_row = await conn.fetchrow('''
                SELECT
                    COALESCE(SUM(points), 0) as total_points,
                    COUNT(DISTINCT DATE(created_at)) as active_days
                FROM leaderboard_activity
                WHERE user_id = $1 AND round_id = $2
            ''', user_id, round_id)

            total_points = stats_row['total_points'] or 0
            active_days = stats_row['active_days'] or 0
            total_score = total_points + (active_days * 5)

            # Get ranks
            rank_spanish = None
            rank_english = None
            rank_combined = None

            if user_row['learning_spanish']:
                rank_spanish = await self._get_user_rank(conn, user_id, 'spanish', round_id)

            if user_row['learning_english']:
                rank_english = await self._get_user_rank(conn, user_id, 'english', round_id)

            rank_combined = await self._get_user_rank(conn, user_id, 'combined', round_id)

            return {
                'username': user_row['username'],
                'total_points': total_points,
                'active_days': active_days,
                'total_score': total_score,
                'rank_spanish': rank_spanish,
                'rank_english': rank_english,
                'rank_combined': rank_combined
            }

    async def _get_user_rank(self, conn, user_id: int, board_type: str, round_id: int) -> Optional[int]:
        """Helper to get user rank on a specific leaderboard for a specific round"""
        where_clause = "lu.learning_spanish = TRUE" if board_type == 'spanish' else (
            "lu.learning_english = TRUE" if board_type == 'english' else "TRUE"
        )

        row = await conn.fetchrow(f'''
            WITH user_stats AS (
                SELECT
                    lu.user_id,
                    COALESCE(SUM(la.points), 0) as total_points,
                    COUNT(DISTINCT DATE(la.created_at)) as active_days
                FROM leaderboard_users lu
                LEFT JOIN leaderboard_activity la
                    ON lu.user_id = la.user_id
                    AND la.round_id = $2
                WHERE lu.opted_in = TRUE
                    AND lu.banned = FALSE
                    AND {where_clause}
                GROUP BY lu.user_id
            ),
            ranked_users AS (
                SELECT
                    user_id,
                    (total_points + (active_days * 5)) as total_score,
                    RANK() OVER (ORDER BY (total_points + (active_days * 5)) DESC) as rank
                FROM user_stats
            )
            SELECT rank FROM ranked_users WHERE user_id = $1
        ''', user_id, round_id)

        return row['rank'] if row else None

    async def get_leaderboard(self, board_type: str, limit: int = 10, round_id: Optional[int] = None) -> list[dict]:
        """Get leaderboard rankings for a specific round (or current round if not specified)"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")

        # If no round_id specified, get current round
        if round_id is None:
            current_round = await self.get_current_round()
            if not current_round:
                return []
            round_id = current_round['round_id']

        where_clause = "lu.learning_spanish = TRUE" if board_type == 'spanish' else (
            "lu.learning_english = TRUE" if board_type == 'english' else "TRUE"
        )

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(f'''
                WITH user_stats AS (
                    SELECT
                        lu.user_id,
                        lu.username,
                        COALESCE(SUM(la.points), 0) as total_points,
                        COUNT(DISTINCT DATE(la.created_at)) as active_days
                    FROM leaderboard_users lu
                    LEFT JOIN leaderboard_activity la
                        ON lu.user_id = la.user_id
                        AND la.round_id = $2
                    WHERE lu.opted_in = TRUE
                        AND lu.banned = FALSE
                        AND {where_clause}
                    GROUP BY lu.user_id, lu.username
                )
                SELECT
                    user_id,
                    username,
                    total_points,
                    active_days,
                    (total_points + (active_days * 5)) as total_score,
                    RANK() OVER (ORDER BY (total_points + (active_days * 5)) DESC) as rank
                FROM user_stats
                ORDER BY total_score DESC
                LIMIT $1
            ''', limit, round_id)

            return [dict(row) for row in rows]

    async def exclude_channel(self, channel_id: int, channel_name: str, admin_id: int) -> bool:
        """Add channel to exclusion list"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO leaderboard_excluded_channels (channel_id, channel_name, added_by)
                VALUES ($1, $2, $3)
                ON CONFLICT (channel_id) DO UPDATE
                SET channel_name = $2, added_by = $3, added_at = CURRENT_TIMESTAMP
            ''', channel_id, channel_name, admin_id)
            return True

    async def include_channel(self, channel_id: int) -> bool:
        """Remove channel from exclusion list"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            result = await conn.execute('''
                DELETE FROM leaderboard_excluded_channels
                WHERE channel_id = $1
            ''', channel_id)
            return result == 'DELETE 1'

    async def is_channel_excluded(self, channel_id: int) -> bool:
        """Check if channel is excluded from leaderboard"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow('''
                SELECT channel_id FROM leaderboard_excluded_channels
                WHERE channel_id = $1
            ''', channel_id)
            return row is not None

    async def get_excluded_channels(self) -> list[dict]:
        """Get all excluded channels"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT channel_id, channel_name, added_by, added_at
                FROM leaderboard_excluded_channels
                ORDER BY added_at DESC
            ''')
            return [dict(row) for row in rows]

    async def get_league_admin_stats(self) -> dict:
        """Get admin statistics for the Language League"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            # Get total opted-in users
            total_row = await conn.fetchrow('''
                SELECT COUNT(*) as total
                FROM leaderboard_users
                WHERE opted_in = TRUE AND banned = FALSE
            ''')

            # Get Spanish learners count
            spanish_row = await conn.fetchrow('''
                SELECT COUNT(*) as count
                FROM leaderboard_users
                WHERE opted_in = TRUE AND banned = FALSE AND learning_spanish = TRUE
            ''')

            # Get English learners count
            english_row = await conn.fetchrow('''
                SELECT COUNT(*) as count
                FROM leaderboard_users
                WHERE opted_in = TRUE AND banned = FALSE AND learning_english = TRUE
            ''')

            # Get banned users count
            banned_row = await conn.fetchrow('''
                SELECT COUNT(*) as count
                FROM leaderboard_users
                WHERE banned = TRUE
            ''')

            # Get total activity in last 30 days
            activity_row = await conn.fetchrow('''
                SELECT COUNT(*) as total_messages
                FROM leaderboard_activity
                WHERE created_at > NOW() - INTERVAL '30 days'
            ''')

            return {
                'total_users': total_row['total'],
                'spanish_learners': spanish_row['count'],
                'english_learners': english_row['count'],
                'banned_users': banned_row['count'],
                'total_messages_30d': activity_row['total_messages']
            }

    # League Rounds Management

    async def get_current_round(self) -> Optional[dict]:
        """Get the currently active round"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow('''
                SELECT round_id, round_number, start_date, end_date, status
                FROM league_rounds
                WHERE status = 'active'
                ORDER BY round_id DESC
                LIMIT 1
            ''')
            return dict(row) if row else None

    async def create_round(self, round_number: int, start_date, end_date) -> int:
        """Create a new league round"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow('''
                INSERT INTO league_rounds (round_number, start_date, end_date, status)
                VALUES ($1, $2, $3, 'active')
                RETURNING round_id
            ''', round_number, start_date, end_date)
            return row['round_id']

    async def end_round(self, round_id: int) -> bool:
        """Mark a round as completed"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            await conn.execute('''
                UPDATE league_rounds
                SET status = 'completed'
                WHERE round_id = $1
            ''', round_id)
            return True

    async def save_round_winners(self, round_id: int, winners_data: list) -> None:
        """Save round winners to database"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            for winner in winners_data:
                await conn.execute('''
                    INSERT INTO league_round_winners
                    (round_id, user_id, username, league_type, rank, total_score, active_days)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                ''', round_id, winner['user_id'], winner['username'],
                winner['league_type'], winner['rank'], winner['total_score'], winner['active_days'])

    async def has_user_won_before(self, user_id: int) -> bool:
        """Check if user has ever won first place in any league"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow('''
                SELECT COUNT(*) as count
                FROM league_round_winners
                WHERE user_id = $1 AND rank = 1
            ''', user_id)
            return row['count'] > 0 if row else False

    async def get_previous_winners(self, user_ids: list[int]) -> set[int]:
        """Get set of user_ids who have won first place before (batch query)"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        if not user_ids:
            return set()
        async with self.pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT DISTINCT user_id
                FROM league_round_winners
                WHERE user_id = ANY($1) AND rank = 1
            ''', user_ids)
            return {row['user_id'] for row in rows}

    async def get_round_by_id(self, round_id: int) -> Optional[dict]:
        """Get round details by ID"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow('''
                SELECT round_id, round_number, start_date, end_date, status
                FROM league_rounds
                WHERE round_id = $1
            ''', round_id)
            return dict(row) if row else None

    async def get_last_round_role_recipients(self) -> set[int]:
        """Get user IDs who received the champion role in the previous completed round"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            # Get the most recent completed round
            last_round = await conn.fetchrow('''
                SELECT round_id FROM league_rounds
                WHERE status = 'completed'
                ORDER BY round_number DESC
                LIMIT 1
            ''')
            if not last_round:
                return set()

            # Get users who received the role in that round
            rows = await conn.fetch('''
                SELECT user_id FROM league_role_recipients
                WHERE round_id = $1
            ''', last_round['round_id'])
            return {row['user_id'] for row in rows}

    async def mark_role_recipients(self, round_id: int, user_ids: list[int]) -> None:
        """Mark which users received the champion role for a round"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        if not user_ids:
            return
        async with self.pool.acquire() as conn:
            for user_id in user_ids:
                await conn.execute('''
                    INSERT INTO league_role_recipients (round_id, user_id)
                    VALUES ($1, $2)
                    ON CONFLICT (round_id, user_id) DO NOTHING
                ''', round_id, user_id)

    async def seed_role_recipients(self, user_ids: list[int]) -> None:
        """
        Seed role recipients for the most recent completed round.
        Used for initial setup/migration when manually tracking who had the role.
        """
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            # Get the most recent completed round
            last_round = await conn.fetchrow('''
                SELECT round_id FROM league_rounds
                WHERE status = 'completed'
                ORDER BY round_number DESC
                LIMIT 1
            ''')
            if not last_round:
                return

            # Insert role recipients
            for user_id in user_ids:
                await conn.execute('''
                    INSERT INTO league_role_recipients (round_id, user_id)
                    VALUES ($1, $2)
                    ON CONFLICT (round_id, user_id) DO NOTHING
                ''', last_round['round_id'], user_id)

    # Practice Card Methods (SRS Vocabulary Practice)

    async def add_practice_card(self, word: str, translation: str, language: str,
                                sentence: str, sentence_with_blank: str) -> Optional[int]:
        """
        Add a practice card to the global card pool.
        Returns card ID or None if duplicate.
        """
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            try:
                row = await conn.fetchrow('''
                    INSERT INTO practice_cards (word, translation, language, sentence, sentence_with_blank)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (word, language) DO NOTHING
                    RETURNING id
                ''', word, translation, language, sentence, sentence_with_blank)
                return row['id'] if row else None
            except Exception as e:
                logging.error(f"Error adding practice card: {e}")
                return None

    async def get_cards_for_language(self, language: str) -> list[dict]:
        """Get all practice cards for a language"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT id, word, translation, language, sentence, sentence_with_blank, created_at
                FROM practice_cards
                WHERE language = $1
                ORDER BY id
            ''', language)
            return [dict(row) for row in rows]

    async def get_due_cards(self, user_id: int, language: str, limit: int = 10) -> list[dict]:
        """
        Get cards due for review for a user.
        Returns cards where next_review <= NOW() ordered by most overdue first.
        """
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT pc.id, pc.word, pc.translation, pc.language,
                       pc.sentence, pc.sentence_with_blank,
                       ucp.interval_days, ucp.ease_factor, ucp.repetitions,
                       ucp.last_review, ucp.next_review
                FROM practice_cards pc
                JOIN user_card_progress ucp ON pc.id = ucp.card_id
                WHERE ucp.user_id = $1
                  AND pc.language = $2
                  AND ucp.next_review <= NOW()
                ORDER BY ucp.next_review ASC
                LIMIT $3
            ''', user_id, language, limit)
            return [dict(row) for row in rows]

    async def get_new_cards(self, user_id: int, language: str, limit: int = 10) -> list[dict]:
        """
        Get cards the user hasn't seen yet.
        """
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT pc.id, pc.word, pc.translation, pc.language,
                       pc.sentence, pc.sentence_with_blank
                FROM practice_cards pc
                WHERE pc.language = $1
                  AND pc.id NOT IN (
                      SELECT card_id FROM user_card_progress WHERE user_id = $2
                  )
                ORDER BY pc.id
                LIMIT $3
            ''', language, user_id, limit)
            return [dict(row) for row in rows]

    async def update_user_progress(self, user_id: int, card_id: int,
                                   interval_days: float, ease_factor: float,
                                   repetitions: int, next_review) -> None:
        """
        Update or create user progress for a card.
        """
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO user_card_progress
                    (user_id, card_id, interval_days, ease_factor, repetitions, last_review, next_review)
                VALUES ($1, $2, $3, $4, $5, NOW(), $6)
                ON CONFLICT (user_id, card_id) DO UPDATE
                SET interval_days = $3,
                    ease_factor = $4,
                    repetitions = $5,
                    last_review = NOW(),
                    next_review = $6
            ''', user_id, card_id, interval_days, ease_factor, repetitions, next_review)

    async def get_card_distractors(self, language: str, exclude_word: str, count: int = 3) -> list[str]:
        """
        Get random words for multiple choice distractors.
        """
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT word FROM practice_cards
                WHERE language = $1 AND word != $2
                ORDER BY RANDOM()
                LIMIT $3
            ''', language, exclude_word, count)
            return [row['word'] for row in rows]

    async def get_practice_stats(self, user_id: int, language: str) -> dict:
        """
        Get practice statistics for a user.
        Returns counts of: new, learning, due, mastered cards.
        """
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            # Total cards for language
            total = await conn.fetchval('''
                SELECT COUNT(*) FROM practice_cards WHERE language = $1
            ''', language)

            # Cards user has progress on
            user_cards = await conn.fetch('''
                SELECT ucp.interval_days, ucp.next_review, ucp.repetitions
                FROM user_card_progress ucp
                JOIN practice_cards pc ON ucp.card_id = pc.id
                WHERE ucp.user_id = $1 AND pc.language = $2
            ''', user_id, language)

            new_count = (total or 0) - len(user_cards)
            due_count = 0
            learning_count = 0
            mastered_count = 0

            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)

            for card in user_cards:
                if card['next_review'] and card['next_review'] <= now:
                    due_count += 1
                elif card['interval_days'] >= 21:
                    mastered_count += 1
                else:
                    learning_count += 1

            return {
                'total': total or 0,
                'new': new_count,
                'learning': learning_count,
                'due': due_count,
                'mastered': mastered_count
            }

    async def get_practice_card_count(self, language: str) -> int:
        """Get total count of practice cards for a language"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            count = await conn.fetchval('''
                SELECT COUNT(*) FROM practice_cards WHERE language = $1
            ''', language)
            return count or 0
