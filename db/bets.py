"""Database mixin for World Cup betting (wallets, bets, match results)."""
import logging
from collections.abc import Callable
from datetime import date
from decimal import Decimal

import asyncpg

from db import DatabaseMixin

logger = logging.getLogger(__name__)


class InsufficientBalanceError(Exception):
    """Raised when a bet's stake exceeds the user's available balance."""


class MatchAlreadySettledError(Exception):
    """Raised when settling a match twice or betting on a settled match."""


class TooManyPendingParlaysError(Exception):
    """Raised when a user already has the max number of pending parlays."""


class WCBetsMixin(DatabaseMixin):
    """Queries for the `wc_bet_wallets`, `wc_bets`, and `wc_match_results` tables."""

    # Key in the `bot_settings` KV store holding the odds multiplier as
    # hundredths (e.g. 150 = 1.50x). Stored as an int because bot_settings
    # is BIGINT-valued; converted to/from Decimal at the boundary so money
    # math never touches a float.
    _ODDS_MULTIPLIER_KEY = "wcbet_odds_multiplier"
    _ODDS_MULTIPLIER_DEFAULT = Decimal("1.5")

    async def get_wc_odds_multiplier(self) -> Decimal:
        """Current odds multiplier applied to all offered lines.

        Returns the configured value (Decimal, 2dp) or the default when
        unset. Reads from the shared `bot_settings` KV store as hundredths.
        """
        row = await self._fetchrow(
            'SELECT setting_value FROM bot_settings WHERE setting_key = $1',
            self._ODDS_MULTIPLIER_KEY,
        )
        if row is None or row["setting_value"] is None:
            return self._ODDS_MULTIPLIER_DEFAULT
        return (Decimal(row["setting_value"]) / 100).quantize(Decimal("0.01"))

    async def set_wc_odds_multiplier(self, multiplier: Decimal) -> None:
        """Persist the odds multiplier (stored as hundredths in bot_settings)."""
        hundredths = int((multiplier * 100).to_integral_value())
        await self._execute(
            'INSERT INTO bot_settings (setting_key, setting_value) VALUES ($1, $2) '
            'ON CONFLICT (setting_key) DO UPDATE SET setting_value = $2',
            self._ODDS_MULTIPLIER_KEY, hundredths,
        )

    # ---------- knockout fixture overrides ----------

    async def get_wc_fixture_overrides(self) -> list[dict]:
        """Return all stored fixture overrides.

        Each row is {match_id, home, away, time_et, source}. ``time_et`` is
        None when the override only resolves teams and keeps the shipped
        time; ``source`` is 'manual' or 'auto'. Loaded at startup and after
        each edit to overlay onto the static fixture list.
        """
        rows = await self._fetch(
            'SELECT match_id, home, away, time_et, source FROM wc_fixture_overrides',
        )
        return [dict(row) for row in rows]

    async def set_wc_fixture_override(
        self, match_id: int, home: str, away: str, time_et: str | None = None,
        *, source: str = 'manual',
    ) -> None:
        """Persist (or update) the resolved teams for a knockout fixture.

        ``time_et`` of None keeps the fixture's shipped kickoff time.
        ``source`` records the origin ('manual' or 'auto').
        """
        await self._execute(
            'INSERT INTO wc_fixture_overrides (match_id, home, away, time_et, source) '
            'VALUES ($1, $2, $3, $4, $5) '
            'ON CONFLICT (match_id) DO UPDATE SET '
            'home = $2, away = $3, time_et = $4, source = $5, updated_at = NOW()',
            match_id, home, away, time_et, source,
        )

    async def set_wc_fixture_override_auto(
        self, match_id: int, home: str, away: str,
    ) -> bool:
        """Insert/update an *auto* (ESPN-sourced) override, never clobbering manual.

        Writes only when no row exists or the existing row's source is
        'auto'. A 'manual' row is left untouched (manual always wins).
        Returns True if a row was written, False if a manual row blocked it.
        Auto overrides never touch ``time_et`` (keep the shipped kickoff).
        """
        result = await self._execute(
            'INSERT INTO wc_fixture_overrides (match_id, home, away, source) '
            "VALUES ($1, $2, $3, 'auto') "
            'ON CONFLICT (match_id) DO UPDATE SET '
            'home = $2, away = $3, updated_at = NOW() '
            "WHERE wc_fixture_overrides.source = 'auto'",
            match_id, home, away,
        )
        # asyncpg returns 'INSERT 0 1' / 'UPDATE 1' on a write, '...0' when the
        # WHERE guard blocks an update of a manual row.
        return result.rstrip().endswith('1')

    async def clear_wc_fixture_override(self, match_id: int) -> bool:
        """Delete an override, reverting the fixture to its shipped values.

        Returns True if a row was removed, False if none existed.
        """
        result = await self._execute(
            'DELETE FROM wc_fixture_overrides WHERE match_id = $1', match_id,
        )
        return result.endswith('1')


    async def _log_balance_event(
        self,
        conn,
        user_id: int,
        delta: int,
        balance: int,
        event: str,
        match_id: int | None = None,
    ) -> None:
        """Insert one row into wc_balance_log inside an existing transaction."""
        await conn.execute(
            'INSERT INTO wc_balance_log (user_id, delta, balance, event, match_id) '
            'VALUES ($1, $2, $3, $4, $5)',
            user_id, delta, balance, event, match_id,
        )
        logger.info(
            "wc_balance_log user=%s event=%s delta=%s balance=%s match=%s",
            user_id, event, delta, balance, match_id,
        )

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
        """
        async with self._pool().acquire() as conn, conn.transaction():
            new_balance = await conn.fetchval(
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
            if new_balance is not None:
                await self._log_balance_event(conn, user_id, amount, new_balance, 'daily_allowance')
            return new_balance

    async def claim_wc_bonus(
        self, user_id: int, amount: int, event_tag: str,
        *, guild_id: int | None = None,
    ) -> int | None:
        """Credit a one-time bonus identified by *event_tag*.

        Returns the new balance, or None if already claimed (an existing
        balance-log row with that event for this user).

        If the user has no wallet and *guild_id* is provided, a wallet is
        created with the bonus as the starting balance.
        """
        async with self._pool().acquire() as conn, conn.transaction():
            already = await conn.fetchval(
                'SELECT 1 FROM wc_balance_log '
                'WHERE user_id = $1 AND event = $2 LIMIT 1',
                user_id, event_tag,
            )
            if already:
                return None
            new_balance = await conn.fetchval(
                '''
                UPDATE wc_bet_wallets
                SET balance = balance + $2, updated_at = NOW()
                WHERE user_id = $1
                RETURNING balance
                ''',
                user_id, amount,
            )
            if new_balance is None and guild_id is not None:
                # No wallet yet — create one with the bonus as starting balance.
                new_balance = await conn.fetchval(
                    '''
                    INSERT INTO wc_bet_wallets (user_id, guild_id, balance)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (user_id) DO NOTHING
                    RETURNING balance
                    ''',
                    user_id, guild_id, amount,
                )
            if new_balance is not None:
                await self._log_balance_event(conn, user_id, amount, new_balance, event_tag)
            return new_balance

    async def place_wc_bet(
        self,
        user_id: int,
        guild_id: int,
        match_id: int,
        outcome: str,
        stake: int,
        odds: Decimal,
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
            await self._log_balance_event(conn, user_id, -stake, new_balance, 'bet_placed', match_id)
            return new_balance

    async def place_wc_parlay(
        self, user_id: int, guild_id: int, stake: int, legs: list[dict],
        *, max_pending: int | None = None,
    ) -> int:
        """Place a parlay (2+ legs) in one transaction. Returns the new balance.

        ``legs`` is a list of {match_id, outcome, odds}. The combined odds are
        computed as the product of leg odds. Raises InsufficientBalanceError
        if the balance can't cover the stake.

        When ``max_pending`` is given, raises TooManyPendingParlaysError if the
        user already has that many pending parlays — checked inside the
        transaction (with FOR UPDATE on the wallet held) so concurrent places
        can't both slip past the cap.
        """
        product = Decimal(1)
        for leg in legs:
            product *= Decimal(str(leg['odds']))
        combined = product.quantize(Decimal('0.01'))
        async with self._pool().acquire() as conn, conn.transaction():
            balance = await conn.fetchval(
                'SELECT balance FROM wc_bet_wallets WHERE user_id = $1 FOR UPDATE',
                user_id,
            )
            if balance is None:
                raise InsufficientBalanceError('no wallet')
            if max_pending is not None:
                pending = await conn.fetchval(
                    "SELECT COUNT(*) FROM wc_parlays "
                    "WHERE user_id = $1 AND status = 'pending'",
                    user_id,
                )
                if pending >= max_pending:
                    raise TooManyPendingParlaysError(f'{pending} >= {max_pending}')
            if balance < stake:
                raise InsufficientBalanceError(f'{balance} < {stake}')
            new_balance = balance - stake
            await conn.execute(
                'UPDATE wc_bet_wallets '
                'SET balance = $2, updated_at = NOW() WHERE user_id = $1',
                user_id, new_balance,
            )
            parlay_id = await conn.fetchval(
                'INSERT INTO wc_parlays (user_id, guild_id, stake, combined_odds) '
                'VALUES ($1, $2, $3, $4) RETURNING id',
                user_id, guild_id, stake, combined,
            )
            for leg in legs:
                await conn.execute(
                    'INSERT INTO wc_parlay_legs (parlay_id, match_id, outcome, odds) '
                    'VALUES ($1, $2, $3, $4)',
                    parlay_id, leg['match_id'], leg['outcome'], Decimal(str(leg['odds'])),
                )
            await self._log_balance_event(conn, user_id, -stake, new_balance, 'parlay_placed')
            return new_balance

    async def get_wc_user_parlays(self, user_id: int, status: str | None = None) -> list[dict]:
        """Return the user's parlays (with legs), optionally filtered by status."""
        if status is None:
            parlays = await self._fetch(
                'SELECT id, stake, combined_odds, status, payout, placed_at '
                'FROM wc_parlays WHERE user_id = $1 ORDER BY placed_at DESC',
                user_id,
            )
        else:
            parlays = await self._fetch(
                'SELECT id, stake, combined_odds, status, payout, placed_at '
                'FROM wc_parlays WHERE user_id = $1 AND status = $2 ORDER BY placed_at DESC',
                user_id, status,
            )
        out: list[dict] = []
        for p in parlays:
            legs = await self._fetch(
                'SELECT match_id, outcome, odds, result FROM wc_parlay_legs '
                'WHERE parlay_id = $1 ORDER BY match_id',
                p['id'],
            )
            row = dict(p)
            row['legs'] = [dict(leg) for leg in legs]
            out.append(row)
        return out

    async def get_wc_user_bets(
        self, user_id: int, status: str | None = None, limit: int | None = None,
    ) -> list:
        """Return the user's bets, optionally filtered by status, newest first.

        When limit is given, only the most recent ``limit`` rows are returned.
        """
        sql = (
            'SELECT user_id, match_id, guild_id, outcome, stake, odds, '
            'status, payout, placed_at, settled_at '
            'FROM wc_bets WHERE user_id = $1'
        )
        args: list = [user_id]
        if status is not None:
            args.append(status)
            sql += f' AND status = ${len(args)}'
        sql += ' ORDER BY placed_at DESC'
        if limit is not None:
            args.append(limit)
            sql += f' LIMIT ${len(args)}'
        return await self._fetch(sql, *args)

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
                    new_balance = await conn.fetchval(
                        'UPDATE wc_bet_wallets '
                        'SET balance = balance + $2, updated_at = NOW() '
                        'WHERE user_id = $1 RETURNING balance',
                        bet['user_id'], amount,
                    )
                    if new_balance is None:
                        logger.error(
                            "wc settle: wallet not found for user %s match %s — payout %s not credited",
                            bet['user_id'], match_id, amount,
                        )
                    await conn.execute(
                        "UPDATE wc_bets SET status = 'won', payout = $3, "
                        'settled_at = NOW() WHERE user_id = $1 AND match_id = $2',
                        bet['user_id'], match_id, amount,
                    )
                    winners += 1
                    total_paid += amount
                    bet_details.append({'user_id': bet['user_id'], 'won': True, 'payout': amount})
                    if new_balance is not None:
                        await self._log_balance_event(
                            conn, bet['user_id'], amount, new_balance, 'bet_won', match_id,
                        )
                else:
                    await conn.execute(
                        "UPDATE wc_bets SET status = 'lost', payout = 0, "
                        'settled_at = NOW() WHERE user_id = $1 AND match_id = $2',
                        bet['user_id'], match_id,
                    )
                    losers += 1
                    bet_details.append({'user_id': bet['user_id'], 'won': False, 'payout': 0})
            parlays = await self._settle_parlay_legs(conn, match_id, outcome, payout_fn)
            return {
                'winners': winners, 'losers': losers, 'total_paid': total_paid,
                'bets': bet_details, 'parlays': parlays,
            }

    async def _settle_parlay_legs(
        self, conn, match_id: int, outcome: str, payout_fn: Callable[[int, Decimal], int],
    ) -> list[dict]:
        """Resolve parlay legs on a settled match and settle completed parlays.

        Runs inside settle_wc_match's transaction. A parlay is lost the moment
        any leg loses; it wins only once every leg has won. Returns summaries
        of parlays that settled in this call (for announcing).
        """
        await conn.execute(
            '''
            UPDATE wc_parlay_legs SET result =
                CASE WHEN outcome = $2 THEN 'won' ELSE 'lost' END
            WHERE match_id = $1 AND result IS NULL
            ''',
            match_id, outcome,
        )
        # Parlays still pending that have a leg on this match are candidates.
        # Use an IN-subquery (not JOIN + DISTINCT) so we can lock the rows:
        # Postgres forbids FOR UPDATE together with DISTINCT.
        candidates = await conn.fetch(
            '''
            SELECT p.id, p.user_id, p.stake, p.combined_odds
            FROM wc_parlays p
            WHERE p.status = 'pending'
              AND p.id IN (
                  SELECT parlay_id FROM wc_parlay_legs WHERE match_id = $1
              )
            FOR UPDATE
            ''',
            match_id,
        )
        settled: list[dict] = []
        for p in candidates:
            legs = await conn.fetch(
                'SELECT result FROM wc_parlay_legs WHERE parlay_id = $1', p['id'],
            )
            results = [leg['result'] for leg in legs]
            if 'lost' in results:
                await conn.execute(
                    "UPDATE wc_parlays SET status = 'lost', payout = 0, "
                    'settled_at = NOW() WHERE id = $1',
                    p['id'],
                )
                settled.append({
                    'user_id': p['user_id'], 'won': False, 'payout': 0,
                    'stake': p['stake'], 'odds': p['combined_odds'],
                })
            elif all(r == 'won' for r in results):
                amount = payout_fn(p['stake'], p['combined_odds'])
                new_balance = await conn.fetchval(
                    'UPDATE wc_bet_wallets '
                    'SET balance = balance + $2, updated_at = NOW() '
                    'WHERE user_id = $1 RETURNING balance',
                    p['user_id'], amount,
                )
                await conn.execute(
                    "UPDATE wc_parlays SET status = 'won', payout = $2, "
                    'settled_at = NOW() WHERE id = $1',
                    p['id'], amount,
                )
                if new_balance is not None:
                    await self._log_balance_event(
                        conn, p['user_id'], amount, new_balance, 'parlay_won',
                    )
                settled.append({
                    'user_id': p['user_id'], 'won': True, 'payout': amount,
                    'stake': p['stake'], 'odds': p['combined_odds'],
                })
            # else: still has pending legs — leave it.
        return settled

    async def reverse_wc_settlement(self, match_id: int) -> dict:
        """Reverse an incorrect settlement: claw back winner payouts, reset all
        bets to pending, fix parlay legs, and delete the result row.

        Returns {"clawed_back": int (users), "total_clawed": int (coins),
        "reset_losers": int, "parlays_reversed": int}.
        """
        async with self._pool().acquire() as conn, conn.transaction():
            # 1. Delete the result row.
            deleted = await conn.execute(
                'DELETE FROM wc_match_results WHERE match_id = $1', match_id,
            )
            if deleted == 'DELETE 0':
                raise ValueError(f"Match {match_id} has no settlement to reverse.")

            # 2. Claw back payouts from incorrect winners.
            winners = await conn.fetch(
                'SELECT user_id, payout FROM wc_bets '
                "WHERE match_id = $1 AND status = 'won' FOR UPDATE",
                match_id,
            )
            clawed_back = 0
            total_clawed = 0
            for bet in winners:
                new_balance = await conn.fetchval(
                    'UPDATE wc_bet_wallets '
                    'SET balance = balance - $2, updated_at = NOW() '
                    'WHERE user_id = $1 RETURNING balance',
                    bet['user_id'], bet['payout'],
                )
                clawed_back += 1
                total_clawed += bet['payout']
                if new_balance is not None:
                    await self._log_balance_event(
                        conn, bet['user_id'], -bet['payout'], new_balance,
                        'settlement_reversal', match_id,
                    )

            # 3. Reset all bets on this match back to pending.
            reset = await conn.execute(
                "UPDATE wc_bets SET status = 'pending', payout = NULL, "
                "settled_at = NULL WHERE match_id = $1 AND status IN ('won', 'lost')",
                match_id,
            )
            reset_losers = int(reset.split()[-1]) - clawed_back

            # 4. Reset parlay legs for this match back to NULL.
            await conn.execute(
                'UPDATE wc_parlay_legs SET result = NULL '
                'WHERE match_id = $1',
                match_id,
            )

            # 5. Reverse parlays that settled (won or lost) due to this match.
            #    A parlay should be reversed if it was settled AFTER or AT the
            #    same time as this match. We find parlays with a leg on this
            #    match that aren't 'pending'.
            settled_parlays = await conn.fetch(
                '''
                SELECT p.id, p.user_id, p.status, p.payout
                FROM wc_parlays p
                WHERE p.status IN ('won', 'lost')
                  AND p.id IN (
                      SELECT parlay_id FROM wc_parlay_legs WHERE match_id = $1
                  )
                FOR UPDATE
                ''',
                match_id,
            )
            parlays_reversed = 0
            for p in settled_parlays:
                # Check if the parlay has other lost legs (from other matches).
                other_lost = await conn.fetchval(
                    'SELECT COUNT(*) FROM wc_parlay_legs '
                    'WHERE parlay_id = $1 AND match_id != $2 AND result = \'lost\'',
                    p['id'], match_id,
                )
                if other_lost > 0:
                    # Parlay would still be lost regardless — leave it.
                    continue
                # Claw back payout if it won.
                if p['status'] == 'won' and p['payout'] > 0:
                    new_balance = await conn.fetchval(
                        'UPDATE wc_bet_wallets '
                        'SET balance = balance - $2, updated_at = NOW() '
                        'WHERE user_id = $1 RETURNING balance',
                        p['user_id'], p['payout'],
                    )
                    total_clawed += p['payout']
                    if new_balance is not None:
                        await self._log_balance_event(
                            conn, p['user_id'], -p['payout'], new_balance,
                            'parlay_reversal', match_id,
                        )
                # Reset parlay to pending.
                await conn.execute(
                    "UPDATE wc_parlays SET status = 'pending', payout = NULL, "
                    'settled_at = NULL WHERE id = $1',
                    p['id'],
                )
                parlays_reversed += 1

            return {
                'clawed_back': clawed_back,
                'total_clawed': total_clawed,
                'reset_losers': reset_losers,
                'parlays_reversed': parlays_reversed,
            }

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
                new_balance = await conn.fetchval(
                    'UPDATE wc_bet_wallets '
                    'SET balance = balance + $2, updated_at = NOW() '
                    'WHERE user_id = $1 RETURNING balance',
                    bet['user_id'], bet['stake'],
                )
                await conn.execute(
                    "UPDATE wc_bets SET status = 'void', settled_at = NOW() "
                    'WHERE user_id = $1 AND match_id = $2',
                    bet['user_id'], match_id,
                )
                refunded += 1
                total_refunded += bet['stake']
                if new_balance is not None:
                    await self._log_balance_event(
                        conn, bet['user_id'], bet['stake'], new_balance, 'bet_refund', match_id,
                    )
            # Void any pending parlay with a leg on this match and refund its stake.
            # IN-subquery (not JOIN + DISTINCT) so the rows can be locked:
            # Postgres forbids FOR UPDATE together with DISTINCT.
            parlays = await conn.fetch(
                '''
                SELECT p.id, p.user_id, p.stake
                FROM wc_parlays p
                WHERE p.status = 'pending'
                  AND p.id IN (
                      SELECT parlay_id FROM wc_parlay_legs WHERE match_id = $1
                  )
                FOR UPDATE
                ''',
                match_id,
            )
            for p in parlays:
                new_balance = await conn.fetchval(
                    'UPDATE wc_bet_wallets '
                    'SET balance = balance + $2, updated_at = NOW() '
                    'WHERE user_id = $1 RETURNING balance',
                    p['user_id'], p['stake'],
                )
                await conn.execute(
                    "UPDATE wc_parlays SET status = 'void', settled_at = NOW() WHERE id = $1",
                    p['id'],
                )
                refunded += 1
                total_refunded += p['stake']
                if new_balance is not None:
                    await self._log_balance_event(
                        conn, p['user_id'], p['stake'], new_balance, 'parlay_refund', match_id,
                    )
            return {'refunded': refunded, 'total_refunded': total_refunded}

    async def cancel_wc_bet(self, user_id: int, match_id: int) -> int:
        """Cancel the user's pending single bet on a match, refunding the stake.

        Deletes the pending row and credits the stake back in one
        transaction, logging a ``bet_cancel`` balance event. Raises
        MatchAlreadySettledError if there is no pending bet to cancel (the
        bet was already settled, voided, or never existed). Returns the new
        balance. Kickoff is enforced by the caller before this is invoked.
        """
        async with self._pool().acquire() as conn, conn.transaction():
            bet = await conn.fetchrow(
                'SELECT stake FROM wc_bets '
                "WHERE user_id = $1 AND match_id = $2 AND status = 'pending' "
                'FOR UPDATE',
                user_id, match_id,
            )
            if bet is None:
                raise MatchAlreadySettledError(str(match_id))
            new_balance = await conn.fetchval(
                'UPDATE wc_bet_wallets '
                'SET balance = balance + $2, updated_at = NOW() '
                'WHERE user_id = $1 RETURNING balance',
                user_id, bet['stake'],
            )
            await conn.execute(
                'DELETE FROM wc_bets WHERE user_id = $1 AND match_id = $2',
                user_id, match_id,
            )
            # A pending bet always has a wallet row (FK-by-convention), so the
            # UPDATE ... RETURNING above cannot miss.
            assert new_balance is not None
            await self._log_balance_event(
                conn, user_id, bet['stake'], new_balance, 'bet_cancel', match_id,
            )
            return new_balance

    async def cancel_wc_parlay(self, user_id: int, parlay_id: int) -> int:
        """Cancel the user's pending parlay, refunding the stake.

        Deletes the parlay and its legs and credits the stake back in one
        transaction, logging a ``parlay_cancel`` balance event. Raises
        MatchAlreadySettledError if there is no pending parlay to cancel.
        Returns the new balance. Kickoff is enforced by the caller (a parlay
        is only cancellable while every leg is still bettable).
        """
        async with self._pool().acquire() as conn, conn.transaction():
            parlay = await conn.fetchrow(
                'SELECT stake FROM wc_parlays '
                "WHERE id = $1 AND user_id = $2 AND status = 'pending' "
                'FOR UPDATE',
                parlay_id, user_id,
            )
            if parlay is None:
                raise MatchAlreadySettledError(str(parlay_id))
            new_balance = await conn.fetchval(
                'UPDATE wc_bet_wallets '
                'SET balance = balance + $2, updated_at = NOW() '
                'WHERE user_id = $1 RETURNING balance',
                user_id, parlay['stake'],
            )
            await conn.execute(
                'DELETE FROM wc_parlay_legs WHERE parlay_id = $1', parlay_id,
            )
            await conn.execute(
                'DELETE FROM wc_parlays WHERE id = $1', parlay_id,
            )
            # A pending parlay always has a wallet row, so the UPDATE above hits.
            assert new_balance is not None
            await self._log_balance_event(
                conn, user_id, parlay['stake'], new_balance, 'parlay_cancel',
            )
            return new_balance

    async def get_wc_settled_match_ids(self) -> set[int]:
        """Return the match_ids that already have a recorded result."""
        rows = await self._fetch('SELECT match_id FROM wc_match_results')
        return {row['match_id'] for row in rows}

    async def get_wc_balance_history(self, user_id: int, limit: int = 15) -> list[dict]:
        """Return the most recent balance log entries for a user."""
        rows = await self._fetch(
            'SELECT delta, balance, event, match_id, created_at '
            'FROM wc_balance_log WHERE user_id = $1 '
            'ORDER BY created_at DESC LIMIT $2',
            user_id, limit,
        )
        return [dict(r) for r in rows]

    async def get_wc_pending_market_board(self, match_ids: list[int]) -> dict[int, dict[str, dict[str, int]]]:
        """Return pending single-bet aggregates per match/outcome.

        Shape:
            {
                match_id: {
                    outcome: {"bettors": int, "staked": int},
                },
            }
        """
        if not match_ids:
            return {}

        rows = await self._fetch(
            '''
            SELECT
                match_id,
                outcome,
                COUNT(*) AS bettors,
                COALESCE(SUM(stake), 0) AS staked
            FROM wc_bets
            WHERE status = 'pending'
              AND match_id = ANY($1::INT[])
            GROUP BY match_id, outcome
            ORDER BY match_id, outcome
            ''',
            match_ids,
        )

        board: dict[int, dict[str, dict[str, int]]] = {}
        for row in rows:
            match_board = board.setdefault(int(row['match_id']), {})
            match_board[str(row['outcome'])] = {
                'bettors': int(row['bettors']),
                'staked': int(row['staked']),
            }
        return board

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

    async def get_wc_user_profile(self, user_id: int, guild_id: int) -> dict:
        """Aggregate betting profile: record, win rate inputs, net profit, rank.

        All derived from wc_bets + wc_bet_wallets — no profile is stored.
        """
        agg = await self._fetchrow(
            '''
            SELECT
                COUNT(*)                                              AS total_bets,
                COUNT(*) FILTER (WHERE status = 'won')                AS wins,
                COUNT(*) FILTER (WHERE status = 'lost')               AS losses,
                COUNT(*) FILTER (WHERE status = 'pending')            AS pending,
                COALESCE(SUM(stake) FILTER (WHERE status = 'pending'), 0) AS pending_staked,
                COALESCE(SUM(payout) FILTER (WHERE status = 'won'), 0)    AS total_won,
                COALESCE(SUM(stake) FILTER (WHERE status IN ('won','lost')), 0) AS settled_staked,
                COALESCE(MAX(payout) FILTER (WHERE status = 'won'), 0)    AS biggest_win,
                COALESCE(MAX(odds) FILTER (WHERE status = 'won'), 0)      AS longest_odds_won
            FROM wc_bets WHERE user_id = $1
            ''',
            user_id,
        )
        wallet = await self._fetchrow(
            'SELECT balance FROM wc_bet_wallets WHERE user_id = $1', user_id,
        )
        balance = int(wallet['balance']) if wallet else 0
        rank = await self._fetchval(
            'SELECT COUNT(*) + 1 FROM wc_bet_wallets '
            'WHERE guild_id = $1 AND balance > $2',
            guild_id, balance,
        )
        # Recent settled outcomes (newest first) for streak detection.
        streak_rows = await self._fetch(
            "SELECT status FROM wc_bets WHERE user_id = $1 "
            "AND status IN ('won','lost') ORDER BY settled_at DESC LIMIT 20",
            user_id,
        )
        return {
            'total_bets': int(agg['total_bets']),
            'wins': int(agg['wins']),
            'losses': int(agg['losses']),
            'pending': int(agg['pending']),
            'pending_staked': int(agg['pending_staked']),
            'total_won': int(agg['total_won']),
            'settled_staked': int(agg['settled_staked']),
            'biggest_win': int(agg['biggest_win']),
            'longest_odds_won': agg['longest_odds_won'],
            'balance': balance,
            'rank': int(rank) if rank is not None else None,
            'recent_settled': [r['status'] for r in streak_rows],
        }

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
