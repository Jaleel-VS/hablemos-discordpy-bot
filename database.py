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

            # Leaderboard excluded channels table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS leaderboard_excluded_channels (
                    channel_id BIGINT PRIMARY KEY,
                    channel_name VARCHAR(255),
                    added_by BIGINT NOT NULL,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
                             channel_id: Optional[int] = None, points: int = 1) -> None:
        """Record user activity for leaderboard"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO leaderboard_activity
                (user_id, activity_type, channel_id, points)
                VALUES ($1, $2, $3, $4)
            ''', user_id, activity_type, channel_id, points)

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

    async def get_user_stats(self, user_id: int, days: int = 30) -> Optional[dict]:
        """Get leaderboard stats for a specific user"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        async with self.pool.acquire() as conn:
            # Get user info
            user_row = await conn.fetchrow('''
                SELECT username, learning_spanish, learning_english
                FROM leaderboard_users
                WHERE user_id = $1 AND opted_in = TRUE AND banned = FALSE
            ''', user_id)

            if not user_row:
                return None

            # Get stats
            stats_row = await conn.fetchrow('''
                SELECT
                    COALESCE(SUM(points), 0) as total_points,
                    COUNT(DISTINCT DATE(created_at)) as active_days
                FROM leaderboard_activity
                WHERE user_id = $1
                AND created_at > NOW() - INTERVAL '30 days'
            ''', user_id)

            total_points = stats_row['total_points'] or 0
            active_days = stats_row['active_days'] or 0
            total_score = total_points + (active_days * 5)

            # Get ranks
            rank_spanish = None
            rank_english = None
            rank_combined = None

            if user_row['learning_spanish']:
                rank_spanish = await self._get_user_rank(conn, user_id, 'spanish', days)

            if user_row['learning_english']:
                rank_english = await self._get_user_rank(conn, user_id, 'english', days)

            rank_combined = await self._get_user_rank(conn, user_id, 'combined', days)

            return {
                'username': user_row['username'],
                'total_points': total_points,
                'active_days': active_days,
                'total_score': total_score,
                'rank_spanish': rank_spanish,
                'rank_english': rank_english,
                'rank_combined': rank_combined
            }

    async def _get_user_rank(self, conn, user_id: int, board_type: str, days: int = 30) -> Optional[int]:
        """Helper to get user rank on a specific leaderboard"""
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
                    AND la.created_at > NOW() - INTERVAL '30 days'
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
        ''', user_id)

        return row['rank'] if row else None

    async def get_leaderboard(self, board_type: str, limit: int = 10) -> list[dict]:
        """Get leaderboard rankings"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")

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
                        AND la.created_at > NOW() - INTERVAL '30 days'
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
            ''', limit)

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
