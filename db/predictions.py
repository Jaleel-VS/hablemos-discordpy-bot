"""Database mixin for World Cup predictions."""
from db import DatabaseMixin


class WCPredictionsMixin(DatabaseMixin):
    """Queries for the `wc_predictions` table."""

    async def upsert_wc_prediction(
        self,
        user_id: int,
        guild_id: int,
        team_role_id: int,
        team_name: str,
    ) -> None:
        """Insert or update a user's tournament-winner prediction."""
        await self._execute(
            '''
            INSERT INTO wc_predictions (user_id, guild_id, team_role_id, team_name, updated_at)
            VALUES ($1, $2, $3, $4, NOW())
            ON CONFLICT (user_id) DO UPDATE
            SET guild_id     = EXCLUDED.guild_id,
                team_role_id = EXCLUDED.team_role_id,
                team_name    = EXCLUDED.team_name,
                updated_at   = NOW()
            ''',
            user_id, guild_id, team_role_id, team_name,
        )

    async def get_wc_prediction(self, user_id: int):
        """Return the user's prediction row, or None if they haven't picked."""
        return await self._fetchrow(
            'SELECT user_id, guild_id, team_role_id, team_name, created_at, updated_at '
            'FROM wc_predictions WHERE user_id = $1',
            user_id,
        )

    async def delete_wc_prediction(self, user_id: int) -> bool:
        """Delete a user's prediction. Return True if a row was removed."""
        result = await self._execute(
            'DELETE FROM wc_predictions WHERE user_id = $1', user_id,
        )
        # asyncpg returns a status string like 'DELETE 1'
        return result.endswith(' 1')

    async def get_all_wc_predictions(self, guild_id: int) -> list:
        """Return every prediction for a guild, ordered by creation time."""
        return await self._fetch(
            'SELECT user_id, team_role_id, team_name, created_at, updated_at '
            'FROM wc_predictions WHERE guild_id = $1 ORDER BY created_at ASC',
            guild_id,
        )

    async def wc_prediction_team_distribution(self, guild_id: int) -> list:
        """Return (team_name, count) rows ordered by count desc, name asc."""
        return await self._fetch(
            '''
            SELECT team_name, COUNT(*) AS picks
            FROM wc_predictions
            WHERE guild_id = $1
            GROUP BY team_name
            ORDER BY picks DESC, team_name ASC
            ''',
            guild_id,
        )

    async def count_wc_predictions(self, guild_id: int) -> int:
        """Return total number of predictions stored for a guild."""
        value = await self._fetchval(
            'SELECT COUNT(*) FROM wc_predictions WHERE guild_id = $1', guild_id,
        )
        return int(value or 0)
