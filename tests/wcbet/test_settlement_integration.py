"""Real-Postgres integration tests for wcbet settlement.

Skipped unless ``TEST_DATABASE_URL`` points at a throwaway Postgres
(these create/drop the wcbet tables). They execute the actual SQL, so
they catch Postgres-only failures the fakes can't — e.g. the parlay
settlement crash (``FOR UPDATE is not allowed with DISTINCT``).

Run locally with, e.g.:
    TEST_DATABASE_URL=postgresql://localhost/wcbet_test pytest tests/wcbet/test_settlement_integration.py
"""
from __future__ import annotations

import os
from decimal import Decimal

import pytest

from cogs.wcbet_cog import betting
from db import Database
from db.bets import TooManyPendingParlaysError

TEST_DB_URL = os.getenv("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DB_URL,
    reason="set TEST_DATABASE_URL to a throwaway Postgres to run settlement integration tests",
)

# Narrowed for type-checkers; the skipif above guarantees it's set at runtime.
DB_URL: str = TEST_DB_URL or ""

GUILD = 1
WC_TABLES = (
    "wc_parlay_legs",
    "wc_parlays",
    "wc_balance_log",
    "wc_bets",
    "wc_match_results",
    "wc_bet_wallets",
    "wc_bet_bans",
)


@pytest.fixture
async def db():
    database = Database(DB_URL)
    await database.connect()  # runs initialize_schema (IF NOT EXISTS)
    assert database.pool is not None
    # Start each test from a clean slate for the wcbet tables only.
    async with database.pool.acquire() as conn:
        await conn.execute(
            "TRUNCATE " + ", ".join(WC_TABLES) + " RESTART IDENTITY CASCADE"
        )
    try:
        yield database
    finally:
        async with database.pool.acquire() as conn:
            await conn.execute(
                "TRUNCATE " + ", ".join(WC_TABLES) + " RESTART IDENTITY CASCADE"
            )
        await database.close()


async def test_settle_match_with_a_parlay_leg(db: Database):
    """A match that has a pending parlay leg must settle without raising.

    Regression for the JOIN+DISTINCT+FOR UPDATE crash.
    """
    user = 100
    await db.create_wc_wallet(user, GUILD, 10_000)

    # A 2-leg parlay: leg on match 25 (home) + leg on match 26 (home).
    await db.place_wc_parlay(
        user, GUILD, stake=200,
        legs=[
            {"match_id": 25, "outcome": "home", "odds": 1.5},
            {"match_id": 26, "outcome": "home", "odds": 2.0},
        ],
    )
    # A straight bet on match 25 too, so settle has both kinds to handle.
    await db.place_wc_bet(user, GUILD, 25, "home", 100, Decimal("1.5"))

    # Settle match 25 home win — must not raise.
    summary = await db.settle_wc_match(
        25, 3, 0, "home", payout_fn=betting.payout,
    )
    assert summary["winners"] == 1  # the straight bet won
    # The parlay still has an unresolved leg (match 26), so it stays pending.
    parlays = await db.get_wc_user_parlays(user, status="pending")
    assert len(parlays) == 1
    leg_25 = next(leg for leg in parlays[0]["legs"] if leg["match_id"] == 25)
    assert leg_25["result"] == "won"

    # Settling the second leg should now resolve the parlay as won.
    summary2 = await db.settle_wc_match(
        26, 1, 0, "home", payout_fn=betting.payout,
    )
    assert summary2["parlays"], "parlay should have settled on its final leg"
    won = await db.get_wc_user_parlays(user, status="won")
    assert len(won) == 1
    # combined 1.5 * 2.0 = 3.0 → 200 stake → 600 payout
    assert won[0]["payout"] == betting.payout(200, Decimal("3.00"))


async def test_place_parlay_rejects_over_pending_cap(db: Database):
    """With max_pending set, a user can't stack more pending parlays.

    Placing up to the cap succeeds; the next place raises. Once one
    settles (freeing a slot), placing succeeds again.
    """
    user = 102
    await db.create_wc_wallet(user, GUILD, 10_000)

    legs = [
        {"match_id": 25, "outcome": "home", "odds": 1.5},
        {"match_id": 26, "outcome": "home", "odds": 2.0},
    ]
    # First two (the cap) succeed.
    await db.place_wc_parlay(user, GUILD, stake=100, legs=legs, max_pending=2)
    await db.place_wc_parlay(user, GUILD, stake=100, legs=legs, max_pending=2)

    # Third is rejected and does not debit the wallet.
    with pytest.raises(TooManyPendingParlaysError):
        await db.place_wc_parlay(user, GUILD, stake=100, legs=legs, max_pending=2)
    wallet = await db.get_wc_wallet(user)
    assert wallet["balance"] == 10_000 - 200  # only the two that landed

    # Settle both legs of one parlay (won) to free a slot.
    await db.settle_wc_match(25, 1, 0, "home", payout_fn=betting.payout)
    await db.settle_wc_match(26, 1, 0, "home", payout_fn=betting.payout)
    pending = await db.get_wc_user_parlays(user, status="pending")
    assert len(pending) == 0  # both parlays shared the same legs, both settled

    # Slots freed — placing succeeds again.
    await db.place_wc_parlay(user, GUILD, stake=100, legs=legs, max_pending=2)
    pending = await db.get_wc_user_parlays(user, status="pending")
    assert len(pending) == 1


async def test_void_match_with_a_parlay_leg(db: Database):
    """Voiding a match with a parlay leg must not raise and refunds stakes."""
    user = 101
    await db.create_wc_wallet(user, GUILD, 10_000)
    await db.place_wc_parlay(
        user, GUILD, stake=300,
        legs=[{"match_id": 25, "outcome": "home", "odds": 1.5}],
    )

    result = await db.void_wc_match(25)
    assert result["refunded"] >= 1
    # Parlay should be void, stake refunded back to 10_000.
    wallet = await db.get_wc_wallet(user)
    assert wallet["balance"] == 10_000
