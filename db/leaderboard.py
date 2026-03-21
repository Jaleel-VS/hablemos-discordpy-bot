
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

    async def is_user_banned(self, user_id: int) -> bool:
        """Check if user is banned from leaderboard"""
        row = await self._fetchrow(
            'SELECT banned FROM leaderboard_users WHERE user_id = $1', user_id,
        )
        return row['banned'] if row else False

    async def get_all_opted_in_users(self) -> list:
        """Get all opted-in user IDs for cache warming"""
        return await self._fetch(
            'SELECT user_id FROM leaderboard_users WHERE opted_in = TRUE'
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
        """Get leaderboard stats for a specific user in a specific round"""
        if round_id is None:
            current_round = await self.get_current_round()
            if not current_round:
                return None
            round_id = current_round['round_id']

        self._check_pool()
        async with self.pool.acquire() as conn:
            user_row = await conn.fetchrow('''
                SELECT username, learning_spanish, learning_english
                FROM leaderboard_users
                WHERE user_id = $1 AND opted_in = TRUE AND banned = FALSE
            ''', user_id)
            if not user_row:
                return None

            stats_row = await conn.fetchrow('''
                SELECT COALESCE(SUM(points), 0) as total_points,
                       COUNT(DISTINCT DATE(created_at)) as active_days
                FROM leaderboard_activity
                WHERE user_id = $1 AND round_id = $2
            ''', user_id, round_id)

            total_points = stats_row['total_points'] or 0
            active_days = stats_row['active_days'] or 0
            total_score = total_points + (active_days * 5)

            rank_spanish = rank_english = None
            if user_row['learning_spanish']:
                rank_spanish = await self._get_user_rank(conn, user_id, 'spanish', round_id)
            if user_row['learning_english']:
                rank_english = await self._get_user_rank(conn, user_id, 'english', round_id)
            rank_combined = await self._get_user_rank(conn, user_id, 'combined', round_id)

            return {
                'username': user_row['username'],
                'total_points': total_points, 'active_days': active_days,
                'total_score': total_score,
                'rank_spanish': rank_spanish, 'rank_english': rank_english,
                'rank_combined': rank_combined,
            }

    async def _get_user_rank(self, conn, user_id: int, board_type: str, round_id: int) -> int | None:
        """Helper to get user rank on a specific leaderboard for a specific round"""
        where_clause = "lu.learning_spanish = TRUE" if board_type == 'spanish' else (
            "lu.learning_english = TRUE" if board_type == 'english' else "TRUE"
        )
        row = await conn.fetchrow(f'''
            WITH user_stats AS (
                SELECT lu.user_id,
                       COALESCE(SUM(la.points), 0) as total_points,
                       COUNT(DISTINCT DATE(la.created_at)) as active_days
                FROM leaderboard_users lu
                LEFT JOIN leaderboard_activity la ON lu.user_id = la.user_id AND la.round_id = $2
                WHERE lu.opted_in = TRUE AND lu.banned = FALSE AND {where_clause}
                GROUP BY lu.user_id
            ),
            ranked_users AS (
                SELECT user_id,
                       (total_points + (active_days * 5)) as total_score,
                       RANK() OVER (ORDER BY (total_points + (active_days * 5)) DESC) as rank
                FROM user_stats
            )
            SELECT rank FROM ranked_users WHERE user_id = $1
        ''', user_id, round_id)
        return row['rank'] if row else None

    async def get_leaderboard(self, board_type: str, limit: int = 10, round_id: int | None = None) -> list[dict]:
        """Get leaderboard rankings for a specific round"""
        if round_id is None:
            current_round = await self.get_current_round()
            if not current_round:
                return []
            round_id = current_round['round_id']

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
        ''', limit, round_id)
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
        """Get admin statistics for the Language League"""
        self._check_pool()
        async with self.pool.acquire() as conn:
            total = await conn.fetchval('''
                SELECT COUNT(*) FROM leaderboard_users WHERE opted_in = TRUE AND banned = FALSE
            ''')
            spanish = await conn.fetchval('''
                SELECT COUNT(*) FROM leaderboard_users
                WHERE opted_in = TRUE AND banned = FALSE AND learning_spanish = TRUE
            ''')
            english = await conn.fetchval('''
                SELECT COUNT(*) FROM leaderboard_users
                WHERE opted_in = TRUE AND banned = FALSE AND learning_english = TRUE
            ''')
            banned = await conn.fetchval(
                'SELECT COUNT(*) FROM leaderboard_users WHERE banned = TRUE'
            )
            msgs = await conn.fetchval('''
                SELECT COUNT(*) FROM leaderboard_activity
                WHERE created_at > NOW() - INTERVAL '30 days'
            ''')
            return {
                'total_users': total, 'spanish_learners': spanish,
                'english_learners': english, 'banned_users': banned,
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
        """Save round winners to database"""
        self._check_pool()
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
        row = await self._fetchrow('''
            SELECT COUNT(*) as count FROM league_round_winners
            WHERE user_id = $1 AND rank = 1
        ''', user_id)
        return row['count'] > 0 if row else False

    async def get_previous_winners(self, user_ids: list[int]) -> set[int]:
        """Get set of user_ids who have won first place before (batch query)"""
        if not user_ids:
            return set()
        rows = await self._fetch('''
            SELECT DISTINCT user_id FROM league_round_winners
            WHERE user_id = ANY($1) AND rank = 1
        ''', user_ids)
        return {row['user_id'] for row in rows}

    async def get_round_by_id(self, round_id: int) -> dict | None:
        """Get round details by ID"""
        row = await self._fetchrow('''
            SELECT round_id, round_number, start_date, end_date, status
            FROM league_rounds WHERE round_id = $1
        ''', round_id)
        return dict(row) if row else None

    async def get_last_round_role_recipients(self) -> set[int]:
        """Get user IDs who received the champion role in the previous completed round"""
        self._check_pool()
        async with self.pool.acquire() as conn:
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
        """Mark which users received the champion role for a round"""
        if not user_ids:
            return
        self._check_pool()
        async with self.pool.acquire() as conn:
            for user_id in user_ids:
                await conn.execute('''
                    INSERT INTO league_role_recipients (round_id, user_id)
                    VALUES ($1, $2) ON CONFLICT (round_id, user_id) DO NOTHING
                ''', round_id, user_id)

    async def seed_role_recipients(self, user_ids: list[int]) -> None:
        """Seed role recipients for the most recent completed round."""
        self._check_pool()
        async with self.pool.acquire() as conn:
            last_round = await conn.fetchrow('''
                SELECT round_id FROM league_rounds
                WHERE status = 'completed' ORDER BY round_number DESC LIMIT 1
            ''')
            if not last_round:
                return
            for user_id in user_ids:
                await conn.execute('''
                    INSERT INTO league_role_recipients (round_id, user_id)
                    VALUES ($1, $2) ON CONFLICT (round_id, user_id) DO NOTHING
                ''', last_round['round_id'], user_id)
