
"""Database mixin for Language League leaderboard queries."""
import asyncio
from datetime import UTC, date, datetime, timedelta

from cogs.league_cog.config import SCORING
from cogs.league_cog.levels import XpGain, progress_for_xp
from cogs.league_cog.profile import (
    LeagueProfile,
    RoundStanding,
    effective_streak,
)
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
        """Opt a user out. Returns False when they weren't opted in."""
        result = await self._execute('''
            UPDATE leaderboard_users
            SET opted_in = FALSE, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = $1 AND opted_in = TRUE
        ''', user_id)
        return result == 'UPDATE 1'

    async def leaderboard_ban_user(self, user_id: int, username: str) -> None:
        """Ban a user, creating an opted-out row if they never joined.

        ``username`` is only stored for a new row; an existing row keeps its own.
        """
        await self._execute('''
            INSERT INTO leaderboard_users (user_id, username, opted_in, banned)
            VALUES ($1, $2, FALSE, TRUE)
            ON CONFLICT (user_id) DO UPDATE
            SET banned = TRUE, updated_at = CURRENT_TIMESTAMP
        ''', user_id, username)

    async def leaderboard_unban_user(self, user_id: int) -> bool:
        """Unban a user. Returns False when they weren't banned."""
        result = await self._execute('''
            UPDATE leaderboard_users
            SET banned = FALSE, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = $1 AND banned = TRUE
        ''', user_id)
        return result == 'UPDATE 1'

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
        Times are in the database session timezone (UTC on the Lightsail DB).
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

    async def record_activity(self, user_id: int, activity_type: str = 'message',
                             channel_id: int | None = None, points: int = 1,
                             round_id: int | None = None, message_id: int | None = None) -> XpGain:
        """Record a counted message and add its points to the user's level XP."""
        async with self._pool().acquire() as conn, conn.transaction():
            await conn.execute('''
                INSERT INTO leaderboard_activity
                (user_id, activity_type, channel_id, points, round_id, message_id)
                VALUES ($1, $2, $3, $4, $5, $6)
            ''', user_id, activity_type, channel_id, points, round_id, message_id)
            # Streak: same UTC day keeps it, the next day extends it, a gap resets it.
            row = await conn.fetchrow('''
                INSERT INTO league_levels
                    (user_id, xp, current_streak, best_streak, last_active_date)
                VALUES ($1, $2, 1, 1, $3)
                ON CONFLICT (user_id) DO UPDATE SET
                    xp = league_levels.xp + EXCLUDED.xp,
                    current_streak = CASE league_levels.last_active_date
                        WHEN $3 THEN league_levels.current_streak
                        WHEN $3 - 1 THEN league_levels.current_streak + 1
                        ELSE 1 END,
                    best_streak = GREATEST(league_levels.best_streak, CASE league_levels.last_active_date
                        WHEN $3 THEN league_levels.current_streak
                        WHEN $3 - 1 THEN league_levels.current_streak + 1
                        ELSE 1 END),
                    last_active_date = $3,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING xp, cards_enabled
            ''', user_id, points, datetime.now(UTC).date())
        xp = int(row['xp'])
        return XpGain(xp_before=xp - points, xp_after=xp, cards_enabled=row['cards_enabled'])

    async def get_league_profile(
        self, user_id: int, round_id: int | None, today: date,
    ) -> LeagueProfile:
        """Everything ``/league profile`` shows. ``round_id`` is the active round, if any."""
        levels = await self._fetchrow('''
            SELECT xp, current_streak, best_streak, last_active_date
            FROM league_levels WHERE user_id = $1
        ''', user_id)
        podium_rows = await self._fetch('''
            SELECT rank, COUNT(*) AS n FROM league_round_winners
            WHERE user_id = $1 GROUP BY rank
        ''', user_id)
        podiums = {row['rank']: int(row['n']) for row in podium_rows}
        champion_weeks = await self._fetchval(
            'SELECT COUNT(*) FROM league_role_recipients WHERE user_id = $1', user_id,
        )
        # Podium scores go back to the first round; full results only to levels launch.
        best_round = await self._fetchval('''
            SELECT MAX(total_score) FROM (
                SELECT total_score FROM league_round_results WHERE user_id = $1
                UNION ALL
                SELECT total_score FROM league_round_winners WHERE user_id = $1
            ) scores
        ''', user_id)
        start = today - timedelta(days=6)
        daily_rows = await self._fetch('''
            SELECT DATE(created_at) AS day, SUM(points) AS points
            FROM leaderboard_activity
            WHERE user_id = $1 AND created_at >= $2
            GROUP BY day
        ''', user_id, datetime(start.year, start.month, start.day))
        by_day = {row['day']: int(row['points']) for row in daily_rows}

        xp, streak, best_streak, last_active = (
            (int(levels['xp']), levels['current_streak'], levels['best_streak'],
             levels['last_active_date'])
            if levels else (0, 0, 0, None)
        )
        return LeagueProfile(
            progress=progress_for_xp(xp),
            streak=effective_streak(streak, last_active, today),
            best_streak=best_streak,
            podiums=(podiums.get(1, 0), podiums.get(2, 0), podiums.get(3, 0)),
            champion_weeks=int(champion_weeks or 0),
            best_round=int(best_round or 0),
            daily_points=tuple(by_day.get(start + timedelta(days=i), 0) for i in range(7)),
            standing=await self._get_round_standing(user_id, round_id) if round_id else None,
        )

    async def _get_round_standing(self, user_id: int, round_id: int) -> RoundStanding | None:
        """The member's place on their board this round; None if not competing."""
        member = await self._fetchrow('''
            SELECT learning_spanish FROM leaderboard_users
            WHERE user_id = $1 AND opted_in = TRUE AND banned = FALSE
        ''', user_id)
        if not member:
            return None
        board = 'spanish' if member['learning_spanish'] else 'english'
        row = await self._fetchrow('''
            WITH user_stats AS (
                SELECT lu.user_id,
                       COALESCE(SUM(la.points), 0) AS points,
                       COUNT(DISTINCT DATE(la.created_at)) AS active_days
                FROM leaderboard_users lu
                LEFT JOIN leaderboard_activity la
                       ON la.user_id = lu.user_id AND la.round_id = $2
                WHERE lu.opted_in = TRUE AND lu.banned = FALSE
                  AND CASE $3::text WHEN 'spanish' THEN lu.learning_spanish
                                    ELSE lu.learning_english END
                GROUP BY lu.user_id
            ),
            ranked AS (
                SELECT user_id, points, active_days,
                       points + active_days * $4 AS score,
                       ROW_NUMBER() OVER w AS rank,
                       LAG(points + active_days * $4) OVER w AS above_score,
                       LEAD(points + active_days * $4) OVER w AS below_score
                FROM user_stats
                WINDOW w AS (ORDER BY points + active_days * $4 DESC, user_id)
            )
            SELECT * FROM ranked WHERE user_id = $1
        ''', user_id, round_id, board, SCORING.ACTIVE_DAY_BONUS_MULTIPLIER)
        if not row:
            return None
        previous_rank = await self._fetchval('''
            SELECT rank FROM league_round_results
            WHERE user_id = $1 AND league_type = $2 AND round_id = (
                SELECT round_id FROM league_rounds WHERE status = 'completed'
                ORDER BY round_number DESC LIMIT 1
            )
        ''', user_id, board)
        combined_rank = await self._get_user_rank(user_id, 'combined', round_id)
        score = int(row['score'])
        return RoundStanding(
            board=board,
            rank=int(row['rank']),
            combined_rank=combined_rank or int(row['rank']),
            points=int(row['points']),
            active_days=int(row['active_days']),
            bonus=int(row['active_days']) * SCORING.ACTIVE_DAY_BONUS_MULTIPLIER,
            previous_rank=previous_rank,
            above_gap=None if row['above_score'] is None else int(row['above_score']) - score,
            below_gap=None if row['below_score'] is None else score - int(row['below_score']),
        )

    async def set_level_cards(self, user_id: int, enabled: bool) -> None:
        """Turn a user's level-up cards on or off."""
        await self._execute('''
            INSERT INTO league_levels (user_id, cards_enabled) VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE
            SET cards_enabled = EXCLUDED.cards_enabled, updated_at = CURRENT_TIMESTAMP
        ''', user_id, enabled)

    async def get_user_stats(self, user_id: int, round_id: int | None = None) -> dict | None:
        """Get leaderboard stats for a specific user in a specific round."""
        if round_id is None:
            current_round = await self.get_current_round()
            if not current_round:
                return None
            round_id_value = int(current_round['round_id'])
        else:
            round_id_value = int(round_id)

        row = await self._fetchrow('''
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
        total_score = total_points + active_days * SCORING.ACTIVE_DAY_BONUS_MULTIPLIER

        # Each rank query takes its own pool connection, so they run in parallel.
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
        """Return the user's position using the displayed board's tie-break."""
        row = await self._fetchrow('''
            WITH user_stats AS (
                SELECT lu.user_id,
                       COALESCE(SUM(la.points), 0) AS total_points,
                       COUNT(DISTINCT DATE(la.created_at)) AS active_days
                FROM leaderboard_users lu
                LEFT JOIN leaderboard_activity la
                       ON la.user_id = lu.user_id AND la.round_id = $2
                WHERE lu.opted_in = TRUE AND lu.banned = FALSE
                  AND CASE $3::text
                      WHEN 'spanish' THEN lu.learning_spanish
                      WHEN 'english' THEN lu.learning_english
                      ELSE TRUE
                  END
                GROUP BY lu.user_id
            ),
            ranked AS (
                SELECT user_id,
                       ROW_NUMBER() OVER (
                           ORDER BY (total_points + active_days * $4) DESC, user_id
                       ) AS rank
                FROM user_stats
            )
            SELECT rank FROM ranked WHERE user_id = $1
        ''', user_id, round_id, board_type, SCORING.ACTIVE_DAY_BONUS_MULTIPLIER)
        return row['rank'] if row else None

    async def get_leaderboard(
        self, board_type: str, limit: int | None = 10, round_id: int | None = None,
    ) -> list[dict]:
        """Leaderboard rankings for a round; ``limit=None`` returns everyone."""
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
                   (total_points + (active_days * $3)) as total_score,
                   ROW_NUMBER() OVER (
                       ORDER BY (total_points + (active_days * $3)) DESC, user_id
                   ) as rank
            FROM user_stats ORDER BY total_score DESC, user_id LIMIT $1
        ''', limit, round_id_value, SCORING.ACTIVE_DAY_BONUS_MULTIPLIER)
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

    async def get_excluded_channels(self) -> list[dict]:
        """Get all excluded channels"""
        rows = await self._fetch('''
            SELECT channel_id, channel_name, added_by, added_at
            FROM leaderboard_excluded_channels ORDER BY added_at DESC
        ''')
        return [dict(row) for row in rows]

    async def get_league_admin_stats(self) -> dict:
        """Get admin statistics for the Language League."""
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

    async def complete_round(
        self,
        round_id: int,
        winners_data: list[dict],
        results: list[dict],
        role_recipient_ids: list[int],
        next_round_number: int,
        next_start: datetime,
        next_end: datetime,
    ) -> int | None:
        """End a round and open the next one in one transaction.

        Saves the winners, every participant's final standing, and the
        champion-role recipients, marks the round completed, and creates the
        next round. Returns the new round's ID, or ``None`` when the round was
        no longer active (another caller already completed it), in which case
        nothing is written.
        """
        async with self._pool().acquire() as conn, conn.transaction():
            result = await conn.execute('''
                UPDATE league_rounds SET status = 'completed'
                WHERE round_id = $1 AND status = 'active'
            ''', round_id)
            if result != 'UPDATE 1':
                return None
            if results:
                await conn.executemany(
                    '''
                    INSERT INTO league_round_results
                        (round_id, user_id, league_type, rank, total_score, active_days)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ''',
                    [
                        (round_id, r['user_id'], r['league_type'], r['rank'],
                         r['total_score'], r['active_days'])
                        for r in results
                    ],
                )
            if winners_data:
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
            if role_recipient_ids:
                await conn.executemany(
                    '''
                    INSERT INTO league_role_recipients (round_id, user_id)
                    VALUES ($1, $2) ON CONFLICT (round_id, user_id) DO NOTHING
                    ''',
                    [(round_id, uid) for uid in role_recipient_ids],
                )
            return await conn.fetchval('''
                INSERT INTO league_rounds (round_number, start_date, end_date, status)
                VALUES ($1, $2, $3, 'active') RETURNING round_id
            ''', next_round_number, next_start, next_end)

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
