"""Database mixin for ticket-arrival subscriptions."""

from db import DatabaseMixin


class TicketSubsMixin(DatabaseMixin):
    """Queries for the ``ticket_subscriptions`` table."""

    async def add_ticket_subscription(
        self, user_id: int, guild_id: int, forum_id: int,
    ) -> bool:
        """Subscribe a user to new-ticket pings for a specific forum.

        Returns True if a new subscription was created, False if the user
        was already subscribed to that forum.
        """
        result = await self._execute(
            '''
            INSERT INTO ticket_subscriptions (user_id, guild_id, forum_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id, guild_id, forum_id) DO NOTHING
            ''',
            user_id, guild_id, forum_id,
        )
        # asyncpg returns e.g. "INSERT 0 1" — the trailing count is rows added.
        return result.endswith("1")

    async def remove_ticket_subscription(
        self, user_id: int, guild_id: int, forum_id: int,
    ) -> bool:
        """Unsubscribe a user from a specific forum. Returns True if a row was removed."""
        result = await self._execute(
            '''
            DELETE FROM ticket_subscriptions
            WHERE user_id = $1 AND guild_id = $2 AND forum_id = $3
            ''',
            user_id, guild_id, forum_id,
        )
        return result.endswith("1")

    async def get_ticket_subscribed_forums(
        self, user_id: int, guild_id: int,
    ) -> list[int]:
        """Return the forum IDs the user is subscribed to in this guild."""
        rows = await self._fetch(
            'SELECT forum_id FROM ticket_subscriptions WHERE user_id = $1 AND guild_id = $2',
            user_id, guild_id,
        )
        return [row['forum_id'] for row in rows]

    async def get_ticket_subscribers(
        self, guild_id: int, forum_id: int,
    ) -> list[int]:
        """Return the user IDs subscribed to a specific forum in this guild."""
        rows = await self._fetch(
            '''
            SELECT user_id FROM ticket_subscriptions
            WHERE guild_id = $1 AND forum_id = $2
            ''',
            guild_id, forum_id,
        )
        return [row['user_id'] for row in rows]

    async def migrate_legacy_ticket_subs(
        self, guild_id: int, forum_ids: list[int],
    ) -> int:
        """Expand legacy rows (forum_id=0) into per-forum subscriptions.

        For each user that has a forum_id=0 row, inserts one row per
        forum in *forum_ids*, then deletes the legacy row.
        Returns the number of users migrated.
        """
        rows = await self._fetch(
            '''
            SELECT user_id FROM ticket_subscriptions
            WHERE guild_id = $1 AND forum_id = 0
            ''',
            guild_id,
        )
        if not rows:
            return 0

        for row in rows:
            uid = row['user_id']
            for fid in forum_ids:
                await self._execute(
                    '''
                    INSERT INTO ticket_subscriptions (user_id, guild_id, forum_id)
                    VALUES ($1, $2, $3)
                    ON CONFLICT DO NOTHING
                    ''',
                    uid, guild_id, fid,
                )
            await self._execute(
                '''
                DELETE FROM ticket_subscriptions
                WHERE user_id = $1 AND guild_id = $2 AND forum_id = 0
                ''',
                uid, guild_id,
            )
        return len(rows)
