
"""Database mixin for Language League leaderboard queries."""
import asyncio

from db import DatabaseMixin


class LeaderboardMixin(DatabaseMixin):
    async def leaderboard_join(self, user_id: int, username: str,
                              learning_spanish: bool, learning_english: bool) -> bool:
        """Add user to leaderboard system"""
        await self._execute('''
            INSERT INTO leaderboard_users
            (user_id, username, opted_in, learning_spanish, learning_english)
            VALUES ($1, $2, TRUE, $3, $4)
            ON CONFLICT (user_id) DO UPDATE
            SET opted_in = TRUE, learning_spanish = $3, learning_english = $4,
                username = $2, updated_at = CURRENT_TIMESTAMP
        ''', user_id, username, learning_spanish, learning_english)
        return True

    async def leaderboard_leave(self, user_id: int) -> bool:
        """Remove user from leaderboard system"""
        result = await self._execute('''
            UPDATE leaderboard_users
            SET opted_in = FALSE, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = $1
        ''', user_id)
        return 'UPDATE' in result

    async def leaderboard_ban_user(self, user_id: int) -> bool:
        """Ban user from leaderboard"""
        result = await self._execute('''
            UPDATE leaderboard_users
            SET banned = TRUE, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = $1
        ''', user_id)
        return 'UPDATE' in result

    async def leaderboard_unban_user(self, user_id: int) -> bool:
        """Unban user from leaderboard"""
        result = await self._execute('''
            UPDATE leaderboard_users
            SET banned = FALSE, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = $1
        ''', user_id)
        return 'UPDATE' in result

    async def is_user_opted_in(self, user_id: int) -> bool:
        """Check if user is opted into leaderboard"""
        row = await self._fetchrow(
            'SELECT opted_in FROM leaderboard_users WHERE user_id = $1', user_id,
        )
        return row['opted_in'] if row else False

    async def get_recent_joiners(self, limit: int = 10) -> list:
        """Return the most recent first-time joiners of the league.

        ``joined_at`` is set on initial insert and preserved across
        re-joins (the upsert only touches ``updated_at``), so this is a
        meaningful “new user” signal rather than a recency-of-any-change
        signal. Banned users are excluded.
        """
        return await self._fetch(
            '''
            SELECT user_id, username, learning_spanish, learning_english,
                   opted_in, joined_at, updated_at
            FROM leaderboard_users
            WHERE banned = FALSE
            ORDER BY joined_at DESC
            LIMIT $1
            ''',
            limit,
        )

    async def get_top_activity_channels(self, days: int = 30, limit: int = 15) -> list:
        """Return channels with the most counted league messages over a window.

        Banned users and already-excluded channels are left in the raw counts
        so the caller can still see, e.g., a recently-excluded channel that
        was the top contributor before exclusion. Callers may filter further.
        """
        return await self._fetch(
            '''
            SELECT channel_id,
                   COUNT(*)                 AS msg_count,
                   COUNT(DISTINCT user_id)  AS unique_users,
                   MAX(created_at)          AS last_activity
            FROM leaderboard_activity
            WHERE created_at >= NOW() - MAKE_INTERVAL(days => $1)
              AND channel_id IS NOT NULL
            GROUP BY channel_id
            ORDER BY msg_count DESC
            LIMIT $2
            ''',
            days, limit,
        )

    async def get_activity_heatmap(self, days: int = 30) -> list:
        """Return (dow, hour, count) rows for a day-of-week × hour heatmap.

        ``dow`` is Postgres ``EXTRACT(DOW FROM ...)`` — 0=Sunday … 6=Saturday.
        Times are in the database session timezone (UTC on Railway).
        """
        return await self._fetch(
            '''
            SELECT EXTRACT(DOW  FROM created_at)::int AS dow,
                   EXTRACT(HOUR FROM created_at)::int AS hour,
                   COUNT(*)                           AS cnt
            FROM leaderboard_activity
            WHERE created_at >= NOW() - MAKE_INTERVAL(days => $1)
            GROUP BY dow, hour
            ''',
            days,
        )

    async def is_user_banned(self, user_id: int) -> bool:
        """Check if user is banned from leaderboard"""
        row = await self._fetchrow(
            'SELECT banned FROM leaderboard_users WHERE user_id = $1', user_id,
        )
        return row['banned'] if row else False

    async def get_all_opted_in_users(self) -> list:
        """Get all opted-in users (with learning flags) for cache warming.

        Returns ``user_id``, ``learning_spanish``, and ``learning_english``
        so callers can warm both the opt-in set and the per-user learning
        map from a single query.
        """
        return await self._fetch(
            'SELECT user_id, learning_spanish, learning_english '
            'FROM leaderboard_users WHERE opted_in = TRUE'
        )

    async def get_all_banned_users(self) -> list:
        """Get all banned user IDs for cache warming"""
        return await self._fetch(
            'SELECT user_id FROM leaderboard_users WHERE banned = TRUE'
        )

    async def get_user_learning_languages(self, user_id: int) -> dict:
        """Get what languages a user is learning."""
        row = await self._fetchrow('''
            SELECT learning_spanish, learning_english FROM leaderboard_users
            WHERE user_id = $1 AND opted_in = TRUE AND banned = FALSE
        ''', user_id)
        if row:
            return {'learning_spanish': row['learning_spanish'], 'learning_english': row['learning_english']}
        return {'learning_spanish': False, 'learning_english': False}

    async def record_activity(self, user_id: int, activity_type: str = 'message',
                             channel_id: int | None = None, points: int = 1,
                             round_id: int | None = None, message_id: int | None = None) -> None:
        """Record user activity for leaderboard"""
        await self._execute('''
            INSERT INTO leaderboard_activity
            (user_id, activity_type, channel_id, points, round_id, message_id)
            VALUES ($1, $2, $3, $4, $5, $6)
        ''', user_id, activity_type, channel_id, points, round_id, message_id)

    async def get_daily_message_count(self, user_id: int) -> int:
        """Get count of messages recorded today for a user"""
        count = await self._fetchval('''
            SELECT COUNT(*) FROM leaderboard_activity
            WHERE user_id = $1 AND activity_type = 'message' AND created_at >= CURRENT_DATE
        ''', user_id)
        return count or 0

    async def get_user_stats(self, user_id: int, round_id: int | None = None) -> dict | None:
        """Get leaderboard stats for a specific user in a specific round."""
        if round_id is None:
            current_round = await self.get_current_round()
            if not current_round:
                return None
            round_id_value = int(current_round['round_id'])
        else:
            round_id_value = int(round_id)

        async with self._pool().acquire() as conn:
            # Single query: user metadata + round aggregates
            row = await conn.fetchrow('''
                SELECT lu.username, lu.learning_spanish, lu.learning_english,
                       COALESCE(SUM(la.points), 0)              AS total_points,
                       COUNT(DISTINCT DATE(la.created_at))      AS active_days
                FROM leaderboard_users lu
                LEFT JOIN leaderboard_activity la
                       ON la.user_id = lu.user_id AND la.round_id = $2
                WHERE lu.user_id = $1 AND lu.opted_in = TRUE AND lu.banned = FALSE
                GROUP BY lu.username, lu.learning_spanish, lu.learning_english
            ''', user_id, round_id_value)
            if not row:
                return None

            total_points = int(row['total_points'] or 0)
            active_days = int(row['active_days'] or 0)
            total_score = total_points + active_days * 5

            # Fetch relevant ranks concurrently — each call acquires its own
            # pool connection, so they run in parallel rather than serially.
            rank_tasks = {
                'combined': self._get_user_rank(user_id, 'combined', round_id_value),
            }
            if row['learning_spanish']:
                rank_tasks['spanish'] = self._get_user_rank(user_id, 'spanish', round_id_value)
            if row['learning_english']:
                rank_tasks['english'] = self._get_user_rank(user_id, 'english', round_id_value)

            keys = list(rank_tasks)
            results = await asyncio.gather(*rank_tasks.values())
            ranks = dict(zip(keys, results, strict=True))

            return {
                'username': row['username'],
                'total_points': total_points,
                'active_days': active_days,
                'total_score': total_score,
                'rank_spanish': ranks.get('spanish'),
                'rank_english': ranks.get('english'),
                'rank_combined': ranks.get('combined'),
            }

    async def _get_user_rank(self, user_id: int, board_type: str, round_id: int) -> int | None:
        """Return the rank of ``user_id`` on the given leaderboard for ``round_id``.

        Uses static per-board queries so Postgres can cache a plan for each shape.
        """
        if board_type == 'spanish':
            sql = '''
                WITH user_stats AS (
                    SELECT lu.user_id,
                           COALESCE(SUM(la.points), 0)          AS total_points,
                           COUNT(DISTINCT DATE(la.created_at))  AS active_days
                    FROM leaderboard_users lu
                    LEFT JOIN leaderboard_activity la
                           ON la.user_id = lu.user_id AND la.round_id = $2
                    WHERE lu.opted_in = TRUE AND lu.banned = FALSE
                      AND lu.learning_spanish = TRUE
                    GROUP BY lu.user_id
                ),
                ranked AS (
                    SELECT user_id,
                           RANK() OVER (
                               ORDER BY (total_points + active_days * 5) DESC
                           ) AS rank
                    FROM user_stats
                )
                SELECT rank FROM ranked WHERE user_id = $1
            '''
        elif board_type == 'english':
            sql = '''
                WITH user_stats AS (
                    SELECT lu.user_id,
                           COALESCE(SUM(la.points), 0)          AS total_points,
                           COUNT(DISTINCT DATE(la.created_at))  AS active_days
                    FROM leaderboard_users lu
                    LEFT JOIN leaderboard_activity la
                           ON la.user_id = lu.user_id AND la.round_id = $2
                    WHERE lu.opted_in = TRUE AND lu.banned = FALSE
                      AND lu.learning_english = TRUE
                    GROUP BY lu.user_id
                ),
                ranked AS (
                    SELECT user_id,
                           RANK() OVER (
                               ORDER BY (total_points + active_days * 5) DESC
                           ) AS rank
                    FROM user_stats
                )
                SELECT rank FROM ranked WHERE user_id = $1
            '''
        else:  # combined
            sql = '''
                WITH user_stats AS (
                    SELECT lu.user_id,
                           COALESCE(SUM(la.points), 0)          AS total_points,
                           COUNT(DISTINCT DATE(la.created_at))  AS active_days
                    FROM leaderboard_users lu
                    LEFT JOIN leaderboard_activity la
                           ON la.user_id = lu.user_id AND la.round_id = $2
                    WHERE lu.opted_in = TRUE AND lu.banned = FALSE
                    GROUP BY lu.user_id
                ),
                ranked AS (
                    SELECT user_id,
                           RANK() OVER (
                               ORDER BY (total_points + active_days * 5) DESC
                           ) AS rank
                    FROM user_stats
                )
                SELECT rank FROM ranked WHERE user_id = $1
            '''
        row = await self._fetchrow(sql, user_id, round_id)
        return row['rank'] if row else None

    async def get_leaderboard(self, board_type: str, limit: int = 10, round_id: int | None = None) -> list[dict]:
        """Get leaderboard rankings for a specific round"""
        if round_id is None:
            current_round = await self.get_current_round()
            if not current_round:
                return []
            round_id_value = int(current_round['round_id'])
        else:
            round_id_value = int(round_id)

        where_clause = "lu.learning_spanish = TRUE" if board_type == 'spanish' else (
            "lu.learning_english = TRUE" if board_type == 'english' else "TRUE"
        )
        rows = await self._fetch(f'''
            WITH user_stats AS (
                SELECT lu.user_id, lu.username,
                       COALESCE(SUM(la.points), 0) as total_points,
                       COUNT(DISTINCT DATE(la.created_at)) as active_days
                FROM leaderboard_users lu
                LEFT JOIN leaderboard_activity la ON lu.user_id = la.user_id AND la.round_id = $2
                WHERE lu.opted_in = TRUE AND lu.banned = FALSE AND {where_clause}
                GROUP BY lu.user_id, lu.username
            )
            SELECT user_id, username, total_points, active_days,
                   (total_points + (active_days * 5)) as total_score,
                   RANK() OVER (ORDER BY (total_points + (active_days * 5)) DESC) as rank
            FROM user_stats ORDER BY total_score DESC LIMIT $1
        ''', limit, round_id_value)
        return [dict(row) for row in rows]

    async def exclude_channel(self, channel_id: int, channel_name: str, admin_id: int) -> bool:
        """Add channel to exclusion list"""
        await self._execute('''
            INSERT INTO leaderboard_excluded_channels (channel_id, channel_name, added_by)
            VALUES ($1, $2, $3)
            ON CONFLICT (channel_id) DO UPDATE
            SET channel_name = $2, added_by = $3, added_at = CURRENT_TIMESTAMP
        ''', channel_id, channel_name, admin_id)
        return True

    async def include_channel(self, channel_id: int) -> bool:
        """Remove channel from exclusion list"""
        result = await self._execute(
            'DELETE FROM leaderboard_excluded_channels WHERE channel_id = $1', channel_id,
        )
        return result == 'DELETE 1'

    async def is_channel_excluded(self, channel_id: int) -> bool:
        """Check if channel is excluded from leaderboard"""
        row = await self._fetchrow(
            'SELECT channel_id FROM leaderboard_excluded_channels WHERE channel_id = $1', channel_id,
        )
        return row is not None

    async def get_excluded_channels(self) -> list[dict]:
        """Get all excluded channels"""
        rows = await self._fetch('''
            SELECT channel_id, channel_name, added_by, added_at
            FROM leaderboard_excluded_channels ORDER BY added_at DESC
        ''')
        return [dict(row) for row in rows]

    async def get_league_admin_stats(self) -> dict:
        """Get admin statistics for the Language League."""
        # Two queries instead of five: leaderboard_users is a single table scan
        # with FILTER aggregates; leaderboard_activity is a separate table.
        row = await self._fetchrow('''
            SELECT
                COUNT(*) FILTER (WHERE opted_in = TRUE AND banned = FALSE)
                    AS total_users,
                COUNT(*) FILTER (WHERE opted_in = TRUE AND banned = FALSE AND learning_spanish = TRUE)
                    AS spanish_learners,
                COUNT(*) FILTER (WHERE opted_in = TRUE AND banned = FALSE AND learning_english = TRUE)
                    AS english_learners,
                COUNT(*) FILTER (WHERE banned = TRUE)
                    AS banned_users
            FROM leaderboard_users
        ''')
        msgs = await self._fetchval('''
            SELECT COUNT(*) FROM leaderboard_activity
            WHERE created_at > NOW() - INTERVAL '30 days'
        ''')
        return {
            'total_users': row['total_users'],
            'spanish_learners': row['spanish_learners'],
            'english_learners': row['english_learners'],
            'banned_users': row['banned_users'],
            'total_messages_30d': msgs,
        }

    # Round management

    async def get_current_round(self) -> dict | None:
        """Get the currently active round"""
        row = await self._fetchrow('''
            SELECT round_id, round_number, start_date, end_date, status
            FROM league_rounds WHERE status = 'active'
            ORDER BY round_id DESC LIMIT 1
        ''')
        return dict(row) if row else None

    async def create_round(self, round_number: int, start_date, end_date) -> int:
        """Create a new league round"""
        row = await self._fetchrow('''
            INSERT INTO league_rounds (round_number, start_date, end_date, status)
            VALUES ($1, $2, $3, 'active') RETURNING round_id
        ''', round_number, start_date, end_date)
        return row['round_id']

    async def end_round(self, round_id: int) -> bool:
        """Mark a round as completed"""
        await self._execute('''
            UPDATE league_rounds SET status = 'completed' WHERE round_id = $1
        ''', round_id)
        return True

    async def save_round_winners(self, round_id: int, winners_data: list) -> None:
        """Save round winners to database."""
        async with self._pool().acquire() as conn:
            await conn.executemany(
                '''
                INSERT INTO league_round_winners
                    (round_id, user_id, username, league_type, rank, total_score, active_days)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ''',
                [
                    (round_id, w['user_id'], w['username'], w['league_type'],
                     w['rank'], w['total_score'], w['active_days'])
                    for w in winners_data
                ],
            )


    async def get_round_by_id(self, round_id: int) -> dict | None:
        """Get round details by ID"""
        row = await self._fetchrow('''
            SELECT round_id, round_number, start_date, end_date, status
            FROM league_rounds WHERE round_id = $1
        ''', round_id)
        return dict(row) if row else None

    async def get_last_round_role_recipients(self) -> set[int]:
        """Get user IDs who received the champion role in the previous completed round"""
        async with self._pool().acquire() as conn:
            last_round = await conn.fetchrow('''
                SELECT round_id FROM league_rounds
                WHERE status = 'completed' ORDER BY round_number DESC LIMIT 1
            ''')
            if not last_round:
                return set()
            rows = await conn.fetch('''
                SELECT user_id FROM league_role_recipients WHERE round_id = $1
            ''', last_round['round_id'])
            return {row['user_id'] for row in rows}

    async def mark_role_recipients(self, round_id: int, user_ids: list[int]) -> None:
        """Mark which users received the champion role for a round."""
        if not user_ids:
            return
        async with self._pool().acquire() as conn:
            await conn.executemany(
                '''
                INSERT INTO league_role_recipients (round_id, user_id)
                VALUES ($1, $2) ON CONFLICT (round_id, user_id) DO NOTHING
                ''',
                [(round_id, uid) for uid in user_ids],
            )

    async def seed_role_recipients(self, user_ids: list[int]) -> None:
        """Seed role recipients for the most recent completed round."""
        if not user_ids:
            return
        async with self._pool().acquire() as conn:
            last_round = await conn.fetchrow('''
                SELECT round_id FROM league_rounds
                WHERE status = 'completed' ORDER BY round_number DESC LIMIT 1
            ''')
            if not last_round:
                return
            await conn.executemany(
                '''
                INSERT INTO league_role_recipients (round_id, user_id)
                VALUES ($1, $2) ON CONFLICT (round_id, user_id) DO NOTHING
                ''',
                [(last_round['round_id'], uid) for uid in user_ids],
            )

    async def get_recent_user_activity(self, user_id: int, limit: int = 3) -> list:
        """Get a user's most recent counted messages from leaderboard_activity."""
        return await self._fetch('''
            SELECT message_id, channel_id, points, created_at, round_id
            FROM leaderboard_activity
            WHERE user_id = $1 AND message_id IS NOT NULL
            ORDER BY created_at DESC
            LIMIT $2
        ''', user_id, limit)
