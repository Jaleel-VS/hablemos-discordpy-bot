"""Database mixin for World Cup betting (wallets, bets, match results)."""
from collections.abc import Callable
from datetime import date
from decimal import Decimal

import asyncpg

from db import DatabaseMixin


class InsufficientBalanceError(Exception):
    """Raised when a bet's stake exceeds the user's available balance."""


class MatchAlreadySettledError(Exception):
    """Raised when settling a match twice or betting on a settled match."""


class WCBetsMixin(DatabaseMixin):
    """Queries for the `wc_bet_wallets`, `wc_bets`, and `wc_match_results` tables."""

    async def get_wc_wallet(self, user_id: int):
        """Return the user's wallet row, or None if they haven't opted in."""
        return await self._fetchrow(
            'SELECT user_id, guild_id, balance, last_allowance_date, created_at, updated_at '
            'FROM wc_bet_wallets WHERE user_id = $1',
            user_id,
        )

    async def create_wc_wallet(
        self, user_id: int, guild_id: int, starting_balance: int,
    ) -> bool:
        """Create a wallet with the starting balance. Return False if one existed."""
        result = await self._execute(
            '''
            INSERT INTO wc_bet_wallets (user_id, guild_id, balance)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id) DO NOTHING
            ''',
            user_id, guild_id, starting_balance,
        )
        # asyncpg returns a status string like 'INSERT 0 1'
        return result.endswith(' 1')

    async def claim_wc_daily_allowance(
        self, user_id: int, amount: int, today: date,
    ) -> int | None:
        """Credit the daily allowance once per day. Return the new balance,
        or None if already claimed today (or no wallet exists).

        Race-safe by construction: a single conditional UPDATE.
        """
        return await self._fetchval(
            '''
            UPDATE wc_bet_wallets
            SET balance = balance + $2,
                last_allowance_date = $3,
                updated_at = NOW()
            WHERE user_id = $1 AND last_allowance_date IS DISTINCT FROM $3
            RETURNING balance
            ''',
            user_id, amount, today,
        )

    async def place_wc_bet(
        self,
        user_id: int,
        guild_id: int,
        match_id: int,
        outcome: str,
        stake: int,
        odds: float,
    ) -> int:
        """Place (or replace) the user's bet on a match in one transaction.

        An existing pending bet on the same match is refunded before the new
        stake is deducted. Raises InsufficientBalanceError if the working
        balance cannot cover the stake, and MatchAlreadySettledError if the
        existing bet on this match is no longer pending. Returns the new
        balance.
        """
        async with self._pool().acquire() as conn, conn.transaction():
            balance = await conn.fetchval(
                'SELECT balance FROM wc_bet_wallets WHERE user_id = $1 FOR UPDATE',
                user_id,
            )
            if balance is None:
                raise InsufficientBalanceError('no wallet')
            existing = await conn.fetchrow(
                'SELECT stake, status FROM wc_bets '
                'WHERE user_id = $1 AND match_id = $2',
                user_id, match_id,
            )
            if existing is not None:
                if existing['status'] != 'pending':
                    raise MatchAlreadySettledError(str(match_id))
                balance += existing['stake']
            if balance < stake:
                raise InsufficientBalanceError(f'{balance} < {stake}')
            new_balance = balance - stake
            await conn.execute(
                'UPDATE wc_bet_wallets '
                'SET balance = $2, updated_at = NOW() WHERE user_id = $1',
                user_id, new_balance,
            )
            await conn.execute(
                '''
                INSERT INTO wc_bets (user_id, match_id, guild_id, outcome, stake, odds)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (user_id, match_id) DO UPDATE
                SET guild_id  = EXCLUDED.guild_id,
                    outcome   = EXCLUDED.outcome,
                    stake     = EXCLUDED.stake,
                    odds      = EXCLUDED.odds,
                    status    = 'pending',
                    payout    = NULL,
                    placed_at = NOW(),
                    settled_at = NULL
                ''',
                user_id, match_id, guild_id, outcome, stake, odds,
            )
            return new_balance

    async def get_wc_user_bets(self, user_id: int, status: str | None = None) -> list:
        """Return the user's bets, optionally filtered by status, newest first."""
        if status is None:
            return await self._fetch(
                'SELECT user_id, match_id, guild_id, outcome, stake, odds, '
                'status, payout, placed_at, settled_at '
                'FROM wc_bets WHERE user_id = $1 ORDER BY placed_at DESC',
                user_id,
            )
        return await self._fetch(
            'SELECT user_id, match_id, guild_id, outcome, stake, odds, '
            'status, payout, placed_at, settled_at '
            'FROM wc_bets WHERE user_id = $1 AND status = $2 ORDER BY placed_at DESC',
            user_id, status,
        )

    async def get_wc_user_bet(self, user_id: int, match_id: int):
        """Return the user's pending bet on a match, or None."""
        return await self._fetchrow(
            'SELECT user_id, match_id, guild_id, outcome, stake, odds, '
            'status, payout, placed_at, settled_at '
            "FROM wc_bets WHERE user_id = $1 AND match_id = $2 AND status = 'pending'",
            user_id, match_id,
        )

    async def settle_wc_match(
        self,
        match_id: int,
        home_score: int,
        away_score: int,
        outcome: str,
        payout_fn: Callable[[int, Decimal], int],
    ) -> dict:
        """Settle every pending bet on a match in one transaction.

        Records the result row (raising MatchAlreadySettledError on a
        duplicate), marks bets won/lost, and credits winners' wallets with
        payout_fn(stake, odds) at each bet's stored odds snapshot.
        Returns {"winners", "losers", "total_paid"}.
        """
        async with self._pool().acquire() as conn, conn.transaction():
            try:
                await conn.execute(
                    'INSERT INTO wc_match_results '
                    '(match_id, home_score, away_score, outcome) '
                    'VALUES ($1, $2, $3, $4)',
                    match_id, home_score, away_score, outcome,
                )
            except asyncpg.UniqueViolationError as exc:
                raise MatchAlreadySettledError(str(match_id)) from exc
            bets = await conn.fetch(
                'SELECT user_id, outcome, stake, odds FROM wc_bets '
                "WHERE match_id = $1 AND status = 'pending' FOR UPDATE",
                match_id,
            )
            winners = 0
            losers = 0
            total_paid = 0
            bet_details: list[dict] = []
            for bet in bets:
                if bet['outcome'] == outcome:
                    amount = payout_fn(bet['stake'], bet['odds'])
                    await conn.execute(
                        'UPDATE wc_bet_wallets '
                        'SET balance = balance + $2, updated_at = NOW() '
                        'WHERE user_id = $1',
                        bet['user_id'], amount,
                    )
                    await conn.execute(
                        "UPDATE wc_bets SET status = 'won', payout = $3, "
                        'settled_at = NOW() WHERE user_id = $1 AND match_id = $2',
                        bet['user_id'], match_id, amount,
                    )
                    winners += 1
                    total_paid += amount
                    bet_details.append({'user_id': bet['user_id'], 'won': True, 'payout': amount})
                else:
                    await conn.execute(
                        "UPDATE wc_bets SET status = 'lost', payout = 0, "
                        'settled_at = NOW() WHERE user_id = $1 AND match_id = $2',
                        bet['user_id'], match_id,
                    )
                    losers += 1
                    bet_details.append({'user_id': bet['user_id'], 'won': False, 'payout': 0})
            return {'winners': winners, 'losers': losers, 'total_paid': total_paid, 'bets': bet_details}

    async def void_wc_match(self, match_id: int) -> dict:
        """Refund every pending stake on a match and mark the bets void.

        Returns {"refunded", "total_refunded"}.
        """
        async with self._pool().acquire() as conn, conn.transaction():
            bets = await conn.fetch(
                'SELECT user_id, stake FROM wc_bets '
                "WHERE match_id = $1 AND status = 'pending' FOR UPDATE",
                match_id,
            )
            refunded = 0
            total_refunded = 0
            for bet in bets:
                await conn.execute(
                    'UPDATE wc_bet_wallets '
                    'SET balance = balance + $2, updated_at = NOW() '
                    'WHERE user_id = $1',
                    bet['user_id'], bet['stake'],
                )
                await conn.execute(
                    "UPDATE wc_bets SET status = 'void', settled_at = NOW() "
                    'WHERE user_id = $1 AND match_id = $2',
                    bet['user_id'], match_id,
                )
                refunded += 1
                total_refunded += bet['stake']
            return {'refunded': refunded, 'total_refunded': total_refunded}

    async def get_wc_settled_match_ids(self) -> set[int]:
        """Return the match_ids that already have a recorded result."""
        rows = await self._fetch('SELECT match_id FROM wc_match_results')
        return {row['match_id'] for row in rows}

    async def get_wc_pending_unsettled(self) -> list[dict]:
        """Return match_ids that have pending bets but no result row yet."""
        rows = await self._fetch(
            '''
            SELECT b.match_id, COUNT(*) AS bet_count, SUM(b.stake) AS total_staked
            FROM wc_bets b
            WHERE b.status = 'pending'
              AND b.match_id NOT IN (SELECT match_id FROM wc_match_results)
            GROUP BY b.match_id
            ORDER BY b.match_id
            '''
        )
        return [dict(r) for r in rows]

    async def get_wc_top_balances(self, guild_id: int, limit: int = 10) -> list[dict]:
        """Return the top wallets by balance for a guild."""
        rows = await self._fetch(
            'SELECT user_id, balance FROM wc_bet_wallets '
            'WHERE guild_id = $1 ORDER BY balance DESC LIMIT $2',
            guild_id, limit,
        )
        return [dict(r) for r in rows]

    async def wc_bet_stats(self, guild_id: int) -> dict:
        """Return aggregate betting stats for a guild."""
        row = await self._fetchrow(
            '''
            SELECT
                (SELECT COUNT(*) FROM wc_bet_wallets WHERE guild_id = $1) AS wallets,
                (SELECT COUNT(*) FROM wc_bets
                 WHERE guild_id = $1 AND status = 'pending') AS pending_bets,
                (SELECT COALESCE(SUM(stake), 0) FROM wc_bets
                 WHERE guild_id = $1 AND status = 'pending') AS total_staked,
                (SELECT MAX(balance) FROM wc_bet_wallets
                 WHERE guild_id = $1) AS top_balance
            ''',
            guild_id,
        )
        return {
            'wallets': int(row['wallets']),
            'pending_bets': int(row['pending_bets']),
            'total_staked': int(row['total_staked']),
            'top_balance': int(row['top_balance']) if row['top_balance'] is not None else None,
        }

    # ---------- moderation (manage_messages tier) ----------

    async def get_wc_user_summary(self, user_id: int) -> dict | None:
        """Return a moderation summary for one user, or None with no wallet.

        Aggregates wallet balance, pending-bet count/stake, and lifetime
        won/lost/void tallies in a single round-trip.
        """
        row = await self._fetchrow(
            '''
            SELECT
                w.balance,
                w.guild_id,
                w.last_allowance_date,
                (SELECT COUNT(*) FROM wc_bets b
                 WHERE b.user_id = w.user_id AND b.status = 'pending') AS pending,
                (SELECT COALESCE(SUM(stake), 0) FROM wc_bets b
                 WHERE b.user_id = w.user_id AND b.status = 'pending') AS pending_stake,
                (SELECT COUNT(*) FROM wc_bets b
                 WHERE b.user_id = w.user_id AND b.status = 'won') AS won,
                (SELECT COALESCE(SUM(payout), 0) FROM wc_bets b
                 WHERE b.user_id = w.user_id AND b.status = 'won') AS won_payout,
                (SELECT COUNT(*) FROM wc_bets b
                 WHERE b.user_id = w.user_id AND b.status = 'lost') AS lost,
                (SELECT COUNT(*) FROM wc_bets b
                 WHERE b.user_id = w.user_id AND b.status = 'void') AS void
            FROM wc_bet_wallets w WHERE w.user_id = $1
            ''',
            user_id,
        )
        if row is None:
            return None
        return {
            'balance': int(row['balance']),
            'guild_id': int(row['guild_id']),
            'last_allowance_date': row['last_allowance_date'],
            'pending': int(row['pending']),
            'pending_stake': int(row['pending_stake']),
            'won': int(row['won']),
            'won_payout': int(row['won_payout']),
            'lost': int(row['lost']),
            'void': int(row['void']),
        }

    async def adjust_wc_balance(self, user_id: int, delta: int) -> int | None:
        """Add `delta` coins to a wallet (negative to deduct), clamped to >= 0.

        Single locked transaction. Returns the new balance, or None if the
        user has no wallet.
        """
        async with self._pool().acquire() as conn, conn.transaction():
            balance = await conn.fetchval(
                'SELECT balance FROM wc_bet_wallets WHERE user_id = $1 FOR UPDATE',
                user_id,
            )
            if balance is None:
                return None
            new_balance = max(0, balance + delta)
            await conn.execute(
                'UPDATE wc_bet_wallets '
                'SET balance = $2, updated_at = NOW() WHERE user_id = $1',
                user_id, new_balance,
            )
            return new_balance

    async def set_wc_bet_ban(
        self, user_id: int, guild_id: int, banned_by: int, reason: str | None,
    ) -> None:
        """Ban (or re-ban) a user from the betting panel."""
        await self._execute(
            '''
            INSERT INTO wc_bet_bans (user_id, guild_id, banned_by, reason)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (user_id) DO UPDATE
            SET guild_id   = EXCLUDED.guild_id,
                banned_by  = EXCLUDED.banned_by,
                reason     = EXCLUDED.reason,
                created_at = NOW()
            ''',
            user_id, guild_id, banned_by, reason,
        )

    async def remove_wc_bet_ban(self, user_id: int) -> bool:
        """Lift a betting ban. Return True if a ban was removed."""
        result = await self._execute(
            'DELETE FROM wc_bet_bans WHERE user_id = $1', user_id,
        )
        return result.endswith(' 1')

    async def is_wc_bet_banned(self, user_id: int) -> bool:
        """Return True if the user is banned from betting."""
        value = await self._fetchval(
            'SELECT 1 FROM wc_bet_bans WHERE user_id = $1', user_id,
        )
        return value is not None
