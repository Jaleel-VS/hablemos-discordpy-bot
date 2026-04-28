"""Database schema initialization and migrations."""
import logging

logger = logging.getLogger(__name__)

async def initialize_schema(pool):
    """Initialize database tables if they don't exist"""
    async with pool.acquire() as conn:
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

        # Intro exempt users table
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS intro_exempt_users (
                user_id BIGINT PRIMARY KEY,
                added_by BIGINT NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
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

        # User card progress table (per-user FSRS tracking)
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS user_card_progress (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                card_id INTEGER NOT NULL REFERENCES practice_cards(id) ON DELETE CASCADE,
                card_json TEXT,
                next_review TIMESTAMPTZ,
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

        # Migration: add card_json and drop SM-2 columns from user_card_progress
        await conn.execute('''
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='user_card_progress' AND column_name='card_json'
                ) THEN
                    ALTER TABLE user_card_progress ADD COLUMN card_json TEXT;
                END IF;
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='user_card_progress' AND column_name='interval_days'
                ) THEN
                    ALTER TABLE user_card_progress
                        DROP COLUMN interval_days,
                        DROP COLUMN ease_factor,
                        DROP COLUMN repetitions,
                        DROP COLUMN last_review;
                END IF;
            END $$;
        ''')

        # Migration: add level, topic, sentence_translation to practice_cards
        await conn.execute('''
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='practice_cards' AND column_name='level'
                ) THEN
                    ALTER TABLE practice_cards
                        ADD COLUMN level VARCHAR(2),
                        ADD COLUMN topic TEXT,
                        ADD COLUMN sentence_translation TEXT;
                END IF;
            END $$;
        ''')

        # Quote banned users table
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS quote_banned_users (
                user_id BIGINT PRIMARY KEY,
                banned_by BIGINT NOT NULL,
                banned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Quote banned channels table
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS quote_banned_channels (
                channel_id BIGINT PRIMARY KEY,
                banned_by BIGINT NOT NULL,
                banned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Quote opt-outs table
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS quote_optouts (
                user_id BIGINT PRIMARY KEY,
                opted_out_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Cog toggle settings
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS cog_settings (
                cog_name VARCHAR(100) PRIMARY KEY,
                enabled BOOLEAN NOT NULL DEFAULT TRUE
            )
        ''')

        # Command usage metrics
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS command_metrics (
                id SERIAL PRIMARY KEY,
                command_name VARCHAR(100) NOT NULL,
                cog_name VARCHAR(100),
                user_id BIGINT NOT NULL,
                guild_id BIGINT,
                channel_id BIGINT,
                is_slash BOOLEAN DEFAULT FALSE,
                failed BOOLEAN DEFAULT FALSE,
                invoked_at TIMESTAMPTZ DEFAULT NOW()
            )
        ''')

        await conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_metrics_invoked
            ON command_metrics(invoked_at)
        ''')

        await conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_metrics_command
            ON command_metrics(command_name, invoked_at)
        ''')

        # Daily rollup table for long-term metrics retention
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS metrics_daily (
                id SERIAL PRIMARY KEY,
                date DATE NOT NULL,
                command_name VARCHAR(100) NOT NULL,
                cog_name VARCHAR(100),
                uses INTEGER NOT NULL DEFAULT 0,
                unique_users INTEGER NOT NULL DEFAULT 0,
                failures INTEGER NOT NULL DEFAULT 0,
                UNIQUE(date, command_name)
            )
        ''')

        await conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_metrics_daily_date
            ON metrics_daily(date)
        ''')

        # Channel interaction tracking (replies and mentions between user pairs)
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS interactions (
                id SERIAL PRIMARY KEY,
                channel_id BIGINT NOT NULL,
                guild_id BIGINT NOT NULL,
                user_a BIGINT NOT NULL,
                user_b BIGINT NOT NULL,
                interaction_type VARCHAR(10) NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        ''')

        await conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_interactions_channel_date
            ON interactions(channel_id, created_at)
        ''')

        await conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_interactions_pair
            ON interactions(user_a, user_b)
        ''')

        # Task management for admins
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id SERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                title VARCHAR(256) NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                status VARCHAR(20) NOT NULL DEFAULT 'todo',
                assignee_ids BIGINT[] NOT NULL DEFAULT '{}',
                created_by BIGINT NOT NULL,
                message_id BIGINT,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        ''')

        await conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_tasks_guild_status
            ON tasks(guild_id, status)
        ''')

        # Exchange partner posts tracking (one active post per user)
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS exchange_posts (
                user_id BIGINT PRIMARY KEY,
                message_id BIGINT NOT NULL,
                channel_id BIGINT NOT NULL,
                post_data JSONB,
                posted_at TIMESTAMPTZ DEFAULT NOW()
            )
        ''')

        await conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_exchange_posts_message
            ON exchange_posts(message_id)
        ''')

        # Migration: add post_data column if missing
        await conn.execute('''
            ALTER TABLE exchange_posts
            ADD COLUMN IF NOT EXISTS post_data JSONB
        ''')

        # Conjugation verbs table (verb metadata)
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS conjugation_verbs (
                id SERIAL PRIMARY KEY,
                infinitive VARCHAR(100) NOT NULL UNIQUE,
                english TEXT NOT NULL,
                category VARCHAR(50),
                level VARCHAR(2),
                frequency_rank INTEGER
            )
        ''')

        await conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_conj_verbs_category
            ON conjugation_verbs(category)
        ''')

        # Conjugation forms table (one row per verb × tense × pronoun)
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS conjugation_forms (
                id SERIAL PRIMARY KEY,
                verb_id INTEGER NOT NULL REFERENCES conjugation_verbs(id) ON DELETE CASCADE,
                tense VARCHAR(50) NOT NULL,
                pronoun VARCHAR(50) NOT NULL,
                form VARCHAR(200) NOT NULL,
                UNIQUE(verb_id, tense, pronoun)
            )
        ''')

        await conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_conj_forms_verb
            ON conjugation_forms(verb_id)
        ''')

        await conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_conj_forms_tense_pronoun
            ON conjugation_forms(tense, pronoun)
        ''')

        logger.info("Database schema initialized")
