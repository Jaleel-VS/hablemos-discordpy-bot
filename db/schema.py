"""Database schema initialization and migrations."""
import logging

logger = logging.getLogger(__name__)

async def initialize_schema(pool):
    """Initialize database tables if they don't exist"""
    async with pool.acquire() as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS notes (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                username VARCHAR(255) NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS introductions (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                accepted BOOLEAN NOT NULL DEFAULT TRUE
            )
        ''')

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

        await conn.execute('''
            ALTER TABLE introductions
            ADD COLUMN IF NOT EXISTS accepted BOOLEAN NOT NULL DEFAULT TRUE
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS intro_exempt_users (
                user_id BIGINT PRIMARY KEY,
                added_by BIGINT NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS bot_settings (
                setting_key VARCHAR(100) PRIMARY KEY,
                setting_value BIGINT NOT NULL
            )
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS feature_settings (
                feature_name VARCHAR(100) PRIMARY KEY,
                enabled BOOLEAN NOT NULL DEFAULT FALSE
            )
        ''')

        await conn.execute('''
            INSERT INTO feature_settings (feature_name, enabled)
            VALUES ('intro_tracker', FALSE)
            ON CONFLICT (feature_name) DO NOTHING
        ''')

        await conn.execute('''
            INSERT INTO feature_settings (feature_name, enabled)
            VALUES ('quote_emoji', TRUE)
            ON CONFLICT (feature_name) DO NOTHING
        ''')

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

        await conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_conversation_lookup
            ON conversations(language, level, category, usage_count)
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS user_conversation_limits (
                user_id BIGINT PRIMARY KEY,
                date DATE DEFAULT CURRENT_DATE,
                conversation_count INTEGER DEFAULT 0
            )
        ''')

        await conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_user_limits_date
            ON user_conversation_limits(user_id, date)
        ''')

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

        await conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_vocab_user_id
            ON vocab_notes(user_id)
        ''')

        await conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_vocab_word
            ON vocab_notes(user_id, word)
        ''')

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

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS leaderboard_excluded_channels (
                channel_id BIGINT PRIMARY KEY,
                channel_name VARCHAR(255),
                added_by BIGINT NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

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

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS quote_banned_users (
                user_id BIGINT PRIMARY KEY,
                banned_by BIGINT NOT NULL,
                banned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS quote_banned_channels (
                channel_id BIGINT PRIMARY KEY,
                banned_by BIGINT NOT NULL,
                banned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS quote_optouts (
                user_id BIGINT PRIMARY KEY,
                opted_out_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS cog_settings (
                cog_name VARCHAR(100) PRIMARY KEY,
                enabled BOOLEAN NOT NULL DEFAULT TRUE
            )
        ''')

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
            ALTER TABLE command_metrics ADD COLUMN IF NOT EXISTS instance_id TEXT
        ''')

        await conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_metrics_invoked
            ON command_metrics(invoked_at)
        ''')

        await conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_metrics_command
            ON command_metrics(command_name, invoked_at)
        ''')

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

        await conn.execute('''
            ALTER TABLE exchange_posts
            ADD COLUMN IF NOT EXISTS post_data JSONB
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS crossword_words (
                id SERIAL PRIMARY KEY,
                word_es TEXT NOT NULL,
                word_en VARCHAR(30) NOT NULL,
                clue_es TEXT NOT NULL,
                clue_en TEXT NOT NULL,
                theme VARCHAR(30) NOT NULL,
                difficulty VARCHAR(10) NOT NULL CHECK (difficulty IN ('beginner', 'advanced')),
                UNIQUE (word_es, theme)
            )
        ''')

        # Storage stays unbounded so schema init cannot truncate existing words.
        await conn.execute('''
            ALTER TABLE crossword_words
            ALTER COLUMN word_es TYPE TEXT
        ''')

        await conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_crossword_difficulty
            ON crossword_words(difficulty)
        ''')

        await conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_crossword_theme
            ON crossword_words(theme)
        ''')

        await conn.execute('DROP TABLE IF EXISTS crossword_scores')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS crossword_active_games (
                channel_id   BIGINT PRIMARY KEY,
                starter_id   BIGINT NOT NULL,
                guild_id     BIGINT,
                is_dm        BOOLEAN NOT NULL DEFAULT FALSE,
                message_id   BIGINT,
                language     VARCHAR(2) NOT NULL,
                difficulty   VARCHAR(16) NOT NULL,
                solved_count INT NOT NULL DEFAULT 0,
                total_words  INT NOT NULL,
                started_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        ''')

        # Migration: carry the canonical game_id so an interrupted game
        # can be logged against crossword_games.
        await conn.execute('''
            ALTER TABLE crossword_active_games
            ADD COLUMN IF NOT EXISTS game_id UUID
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS crossword_games (
                game_id         UUID PRIMARY KEY,
                guild_id        BIGINT,
                channel_id      BIGINT NOT NULL,
                starter_id      BIGINT NOT NULL,
                difficulty      VARCHAR(16) NOT NULL,
                language        VARCHAR(2) NOT NULL,
                total_words     INT NOT NULL,
                words_solved    INT NOT NULL DEFAULT 0,
                hints_used      INT NOT NULL DEFAULT 0,
                completion      VARCHAR(16) NOT NULL,
                started_at      TIMESTAMPTZ NOT NULL,
                ended_at        TIMESTAMPTZ NOT NULL,
                elapsed_seconds REAL NOT NULL
            )
        ''')
        await conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_cw_games_started
            ON crossword_games(started_at)
        ''')
        await conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_cw_games_channel
            ON crossword_games(channel_id)
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS crossword_participants (
                game_id       UUID NOT NULL REFERENCES crossword_games(game_id) ON DELETE CASCADE,
                user_id       BIGINT NOT NULL,
                display_name  TEXT NOT NULL,
                words_solved  INT NOT NULL DEFAULT 0,
                is_starter    BOOLEAN NOT NULL DEFAULT FALSE,
                PRIMARY KEY (game_id, user_id)
            )
        ''')
        await conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_cw_participants_user
            ON crossword_participants(user_id)
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS crossword_word_events (
                id               SERIAL PRIMARY KEY,
                game_id          UUID NOT NULL REFERENCES crossword_games(game_id) ON DELETE CASCADE,
                word             TEXT NOT NULL,
                language         VARCHAR(2) NOT NULL,
                difficulty       VARCHAR(16) NOT NULL,
                solved           BOOLEAN NOT NULL,
                solved_by        BIGINT,
                seconds_to_solve REAL,
                had_hint         BOOLEAN NOT NULL DEFAULT FALSE
            )
        ''')
        await conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_cw_events_word
            ON crossword_word_events(word, language)
        ''')
        await conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_cw_events_game
            ON crossword_word_events(game_id)
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS dictation_sentences (
                id SERIAL PRIMARY KEY,
                language VARCHAR(2) NOT NULL CHECK (language IN ('es', 'en')),
                level VARCHAR(15) NOT NULL CHECK (level IN ('beginner', 'intermediate')),
                sentence TEXT NOT NULL,
                audio_url TEXT,
                created_at TIMESTAMPTZ DEFAULT now(),
                UNIQUE (language, sentence)
            )
        ''')

        await conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_dictation_lang_level
            ON dictation_sentences(language, level)
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS dictation_scores (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                sentence_id INTEGER NOT NULL REFERENCES dictation_sentences(id) ON DELETE CASCADE,
                score INTEGER NOT NULL CHECK (score >= 0 AND score <= 4),
                user_answer TEXT NOT NULL,
                attempted_at TIMESTAMPTZ DEFAULT now()
            )
        ''')

        await conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_dictation_scores_user
            ON dictation_scores(user_id)
        ''')

        await conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_dictation_scores_sentence
            ON dictation_scores(sentence_id)
        ''')

        # Retired tournament data is intentionally removed on existing databases.
        await conn.execute('DROP TABLE IF EXISTS wc_parlay_legs CASCADE')
        await conn.execute('DROP TABLE IF EXISTS wc_parlays CASCADE')
        await conn.execute('DROP TABLE IF EXISTS wc_bets CASCADE')
        await conn.execute('DROP TABLE IF EXISTS wc_balance_log CASCADE')
        await conn.execute('DROP TABLE IF EXISTS wc_bet_wallets CASCADE')
        await conn.execute('DROP TABLE IF EXISTS wc_match_results CASCADE')
        await conn.execute('DROP TABLE IF EXISTS wc_bet_bans CASCADE')
        await conn.execute('DROP TABLE IF EXISTS wc_predictions CASCADE')
        await conn.execute('DROP TABLE IF EXISTS wc_fixture_overrides CASCADE')

        # Removed features: nogif_restrictions, vocab_card_pool and vocab_card_catches
        # are no longer created. Databases created earlier still have them; see
        # db/privacy.py (_LEGACY_DELETES). Drop them with a script when not needed.

        # Ticket-arrival subscriptions — mods who opt in to be pinged when a
        # new moderation ticket (forum thread) is opened.
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS ticket_subscriptions (
                user_id      BIGINT NOT NULL,
                guild_id     BIGINT NOT NULL,
                created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (user_id, guild_id)
            )
        ''')

        await conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_ticket_subscriptions_guild
            ON ticket_subscriptions(guild_id)
        ''')

        # Migration: add per-forum granularity to ticket subscriptions.
        # Adds a forum_id column (0 = legacy "all forums" subscription),
        # drops the old (user_id, guild_id) PK, and re-creates as
        # (user_id, guild_id, forum_id).
        await conn.execute('''
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='ticket_subscriptions' AND column_name='forum_id'
                ) THEN
                    ALTER TABLE ticket_subscriptions
                        ADD COLUMN forum_id BIGINT NOT NULL DEFAULT 0;
                    ALTER TABLE ticket_subscriptions
                        DROP CONSTRAINT ticket_subscriptions_pkey;
                    ALTER TABLE ticket_subscriptions
                        ADD PRIMARY KEY (user_id, guild_id, forum_id);
                END IF;
            END $$;
        ''')

        # Pre-aggregated hourly counts per channel per native-role type.
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS channel_stats (
                channel_id   BIGINT NOT NULL,
                role_type    TEXT NOT NULL,
                hour_bucket  TIMESTAMPTZ NOT NULL,
                msg_count    INT NOT NULL DEFAULT 0,
                PRIMARY KEY (channel_id, role_type, hour_bucket)
            )
        ''')

        await conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_channel_stats_bucket
            ON channel_stats(hour_bucket)
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS user_message_counts (
                user_id      BIGINT NOT NULL,
                hour_bucket  TIMESTAMPTZ NOT NULL,
                msg_count    INT NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, hour_bucket)
            )
        ''')

        await conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_user_message_counts_bucket
            ON user_message_counts(hour_bucket)
        ''')

        # ── Stats: user adoption tracking (no PII) ──
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS user_activity (
                user_id     BIGINT PRIMARY KEY,
                role_type   TEXT NOT NULL,
                first_seen  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                last_seen   TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        ''')

        await conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_user_activity_first_seen
            ON user_activity(first_seen)
        ''')

        await conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_user_activity_last_seen
            ON user_activity(last_seen)
        ''')

        # ── Stats: per-user activity-clock timezone preference ──
        # Whole-hour UTC offset the $myclock command uses to label a user's
        # hour-of-day chart. Stored once so the picker only appears the first
        # time. Offset is an integer hour in [-12, 14] (see StatsMixin).
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS user_clock_prefs (
                user_id     BIGINT PRIMARY KEY,
                utc_offset  SMALLINT NOT NULL,
                updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        ''')

        # ── World clock: up to 12 labelled zones per member ($clock) ──
        # zone is an IANA name or a fixed "UTC+05:30" key (worldclock_cog.zones).
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS user_world_clocks (
                user_id     BIGINT NOT NULL,
                label       TEXT NOT NULL,
                zone        TEXT NOT NULL,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        ''')

        await conn.execute('''
            CREATE UNIQUE INDEX IF NOT EXISTS idx_user_world_clocks_label
            ON user_world_clocks (user_id, lower(label))
        ''')

        # ── Spotify: now-playing opt-ins ──
        # Sharing is off by default. A row means the member allows
        # $nowplaying / $np2 to show their Spotify activity.
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS spotify_optins (
                user_id      BIGINT PRIMARY KEY,
                opted_in_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        ''')

        # Bilingual facts: channel-level progress, no user IDs or message content.
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS fun_facts (
                id TEXT PRIMARY KEY,
                es TEXT NOT NULL,
                en TEXT NOT NULL,
                source_name TEXT NOT NULL,
                source_url TEXT NOT NULL
            )
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS fact_cycles (
                channel_id BIGINT PRIMARY KEY,
                last_fact_id TEXT REFERENCES fun_facts(id) ON DELETE SET NULL
            )
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS fact_seen (
                channel_id BIGINT NOT NULL REFERENCES fact_cycles(channel_id) ON DELETE CASCADE,
                fact_id TEXT NOT NULL REFERENCES fun_facts(id) ON DELETE CASCADE,
                PRIMARY KEY (channel_id, fact_id)
            )
        ''')

        # RSS teasers and channel-level reading progress; no reader user IDs.
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS good_news_articles (
                url TEXT PRIMARY KEY,
                language TEXT NOT NULL,
                source_name TEXT NOT NULL,
                title TEXT NOT NULL,
                excerpt TEXT NOT NULL,
                published_at TIMESTAMPTZ NOT NULL
            )
        ''')
        await conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_good_news_recent
            ON good_news_articles(language, published_at DESC)
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS good_news_channels (
                channel_id BIGINT PRIMARY KEY
            )
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS good_news_seen (
                channel_id BIGINT NOT NULL REFERENCES good_news_channels(channel_id) ON DELETE CASCADE,
                url TEXT NOT NULL REFERENCES good_news_articles(url) ON DELETE CASCADE,
                PRIMARY KEY (channel_id, url)
            )
        ''')

        # Deploy that owns the Discord session; no user data.
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS bot_instance (
                singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
                deploy_version BIGINT NOT NULL,
                instance_id TEXT NOT NULL,
                claimed_at TIMESTAMPTZ NOT NULL
            )
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS bot_instance_events (
                id BIGSERIAL PRIMARY KEY,
                deploy_version BIGINT NOT NULL,
                instance_id TEXT NOT NULL,
                deploy_sha TEXT NOT NULL,
                event TEXT NOT NULL,
                detail JSONB NOT NULL DEFAULT '{}',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        ''')
        await conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_bot_instance_events_created
            ON bot_instance_events(created_at)
        ''')

        logger.info("Database schema initialized")
