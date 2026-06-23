"""Database mixin for ticket-arrival subscriptions."""
from db import DatabaseMixin


class TicketSubsMixin(DatabaseMixin):
    """Queries for the ``ticket_subscriptions`` table."""

    async def add_ticket_subscription(self, user_id: int, guild_id: int) -> bool:
        """Subscribe a user to new-ticket pings.

        Returns True if a new subscription was created, False if the user
        was already subscribed.
        """
        result = await self._execute(
            '''
            INSERT INTO ticket_subscriptions (user_id, guild_id)
            VALUES ($1, $2)
            ON CONFLICT (user_id, guild_id) DO NOTHING
            ''',
            user_id, guild_id,
        )
        # asyncpg returns e.g. "INSERT 0 1" — the trailing count is rows added.
        return result.endswith("1")

    async def remove_ticket_subscription(self, user_id: int, guild_id: int) -> bool:
        """Unsubscribe a user. Returns True if a row was removed."""
        result = await self._execute(
            'DELETE FROM ticket_subscriptions WHERE user_id = $1 AND guild_id = $2',
            user_id, guild_id,
        )
        return result.endswith("1")

    async def is_ticket_subscribed(self, user_id: int, guild_id: int) -> bool:
        """Return True if the user is subscribed in this guild."""
        row = await self._fetchrow(
            'SELECT 1 FROM ticket_subscriptions WHERE user_id = $1 AND guild_id = $2',
            user_id, guild_id,
        )
        return row is not None

    async def get_ticket_subscribers(self, guild_id: int) -> list[int]:
        """Return the user IDs subscribed to new-ticket pings in this guild."""
        rows = await self._fetch(
            'SELECT user_id FROM ticket_subscriptions WHERE guild_id = $1',
            guild_id,
        )
        return [row['user_id'] for row in rows]
