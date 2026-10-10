"""Database mixin for Spotify now-playing opt-ins."""
from db import DatabaseMixin


class SpotifyMixin(DatabaseMixin):
    """Queries for the ``spotify_optins`` table.

    Sharing is off by default: a member's listening activity is only shown
    once they have a row here.
    """

    async def spotify_optin(self, user_id: int) -> bool:
        """Opt a user in to Spotify sharing. Returns False if already opted in."""
        result = await self._execute(
            '''
            INSERT INTO spotify_optins (user_id) VALUES ($1)
            ON CONFLICT (user_id) DO NOTHING
            ''',
            user_id,
        )
        return result == 'INSERT 0 1'

    async def spotify_optout(self, user_id: int) -> bool:
        """Opt a user out of Spotify sharing. Returns False if already opted out."""
        result = await self._execute(
            'DELETE FROM spotify_optins WHERE user_id = $1', user_id,
        )
        return result == 'DELETE 1'

    async def is_spotify_opted_in(self, user_id: int) -> bool:
        """Check whether a user has opted in to Spotify sharing."""
        row = await self._fetchrow(
            'SELECT user_id FROM spotify_optins WHERE user_id = $1', user_id,
        )
        return row is not None
