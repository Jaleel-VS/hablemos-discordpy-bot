from db import DatabaseMixin


class QuotesMixin(DatabaseMixin):
    async def quote_ban_user(self, user_id: int, banned_by: int) -> bool:
        """Ban a user from using quote commands"""
        await self._execute('''
            INSERT INTO quote_banned_users (user_id, banned_by)
            VALUES ($1, $2) ON CONFLICT (user_id) DO NOTHING
        ''', user_id, banned_by)
        return True

    async def quote_unban_user(self, user_id: int) -> bool:
        """Unban a user from quote commands"""
        result = await self._execute(
            'DELETE FROM quote_banned_users WHERE user_id = $1', user_id,
        )
        return result == 'DELETE 1'

    async def is_quote_banned(self, user_id: int) -> bool:
        """Check if a user is banned from quote commands"""
        row = await self._fetchrow(
            'SELECT user_id FROM quote_banned_users WHERE user_id = $1', user_id,
        )
        return row is not None

    async def quote_ban_channel(self, channel_id: int, banned_by: int) -> bool:
        """Ban a channel from quote usage"""
        await self._execute('''
            INSERT INTO quote_banned_channels (channel_id, banned_by)
            VALUES ($1, $2) ON CONFLICT (channel_id) DO NOTHING
        ''', channel_id, banned_by)
        return True

    async def quote_unban_channel(self, channel_id: int) -> bool:
        """Unban a channel from quote usage"""
        result = await self._execute(
            'DELETE FROM quote_banned_channels WHERE channel_id = $1', channel_id,
        )
        return result == 'DELETE 1'

    async def is_quote_channel_banned(self, channel_id: int) -> bool:
        """Check if a channel is banned from quote usage"""
        row = await self._fetchrow(
            'SELECT channel_id FROM quote_banned_channels WHERE channel_id = $1', channel_id,
        )
        return row is not None

    async def get_quote_banned_channels(self) -> list[dict]:
        """Get all quote-banned channels"""
        rows = await self._fetch('''
            SELECT channel_id, banned_by, banned_at
            FROM quote_banned_channels ORDER BY banned_at DESC
        ''')
        return [dict(row) for row in rows]

    async def quote_optout(self, user_id: int) -> bool:
        """Opt a user out of being quoted"""
        await self._execute('''
            INSERT INTO quote_optouts (user_id) VALUES ($1)
            ON CONFLICT (user_id) DO NOTHING
        ''', user_id)
        return True

    async def quote_optin(self, user_id: int) -> bool:
        """Opt a user back into being quoted"""
        result = await self._execute(
            'DELETE FROM quote_optouts WHERE user_id = $1', user_id,
        )
        return result == 'DELETE 1'

    async def is_quote_opted_out(self, user_id: int) -> bool:
        """Check if a user has opted out of being quoted"""
        row = await self._fetchrow(
            'SELECT user_id FROM quote_optouts WHERE user_id = $1', user_id,
        )
        return row is not None
