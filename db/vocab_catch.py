"""Database mixin for the Vocab Catch minigame.

Two tables (see `db/schema.py`):
- `vocab_card_pool`   — curated shared word bank cards spawn from.
                        Bidirectional: each card has `word_es` + `word_en`.
- `vocab_card_catches`— per-user inventory; duplicates bump `count`.

Scoring is derived from rarity at read time (the cog owns the
rarity→points mapping), so no points column is stored.
"""
import random

from db import DatabaseMixin

# Columns selected for a full card row (shared by the read queries).
_CARD_COLS = (
    "card_id, word_es, word_en, part_of_speech, gender, "
    "example_es, example_en, rarity"
)


class VocabCatchMixin(DatabaseMixin):
    """Queries for `vocab_card_pool` and `vocab_card_catches`."""

    async def get_random_card(
        self, rarity_weights: dict[int, int] | None = None,
    ) -> dict | None:
        """Pick a random active card, weighted by rarity.

        `rarity_weights` maps tier (1..5) -> relative weight. A rarity is
        chosen by weight first, then a uniform card within that rarity; if
        that rarity has no active cards, the remaining rarities are tried
        in descending-weight order so a spawn never silently fails while
        cards exist. Returns None only when the pool is empty.
        """
        weights = rarity_weights or {1: 60, 2: 25, 3: 10, 4: 4, 5: 1}
        tiers = sorted(weights, key=lambda t: weights[t], reverse=True)
        chosen = random.choices(tiers, weights=[weights[t] for t in tiers], k=1)[0]
        order = [chosen] + [t for t in tiers if t != chosen]
        for tier in order:
            row = await self._fetchrow(
                f'SELECT {_CARD_COLS} '
                'FROM vocab_card_pool WHERE active = TRUE AND rarity = $1 '
                'ORDER BY random() LIMIT 1',
                tier,
            )
            if row is not None:
                return dict(row)
        return None

    async def get_card(self, card_id: int) -> dict | None:
        """Return one card by id (regardless of active flag), or None."""
        row = await self._fetchrow(
            f'SELECT {_CARD_COLS}, active FROM vocab_card_pool WHERE card_id = $1',
            card_id,
        )
        return dict(row) if row else None

    async def record_catch(self, user_id: int, card_id: int) -> int:
        """Upsert a catch, incrementing the count. Returns the new count."""
        row = await self._fetchrow(
            'INSERT INTO vocab_card_catches (user_id, card_id) VALUES ($1, $2) '
            'ON CONFLICT (user_id, card_id) DO UPDATE '
            'SET count = vocab_card_catches.count + 1, last_caught = NOW() '
            'RETURNING count',
            user_id, card_id,
        )
        return row['count']

    async def get_user_collection(self, user_id: int, limit: int = 50) -> list[dict]:
        """The user's caught cards (newest first), joined with card data."""
        rows = await self._fetch(
            'SELECT c.card_id, c.count, c.first_caught, c.last_caught, '
            'p.word_es, p.word_en, p.part_of_speech, p.gender, '
            'p.example_es, p.example_en, p.rarity '
            'FROM vocab_card_catches c '
            'JOIN vocab_card_pool p ON p.card_id = c.card_id '
            'WHERE c.user_id = $1 '
            'ORDER BY c.last_caught DESC LIMIT $2',
            user_id, limit,
        )
        return [dict(r) for r in rows]

    async def get_collection_stats(self, user_id: int) -> dict:
        """Distinct cards owned, total catches, and per-rarity distinct counts."""
        totals = await self._fetchrow(
            'SELECT COUNT(*) AS distinct_cards, COALESCE(SUM(count), 0) AS total_catches '
            'FROM vocab_card_catches WHERE user_id = $1',
            user_id,
        )
        rarity_rows = await self._fetch(
            'SELECT p.rarity, COUNT(*) AS n FROM vocab_card_catches c '
            'JOIN vocab_card_pool p ON p.card_id = c.card_id '
            'WHERE c.user_id = $1 GROUP BY p.rarity',
            user_id,
        )
        return {
            'distinct_cards': totals['distinct_cards'],
            'total_catches': int(totals['total_catches']),
            'by_rarity': {r['rarity']: r['n'] for r in rarity_rows},
        }

    async def get_catch_leaderboard(
        self, rarity_points: dict[int, int], limit: int = 10,
    ) -> list[dict]:
        """Top users by total points (sum of rarity_points × count).

        Points are computed in SQL from the passed mapping via a CASE so a
        single query ranks everyone. Ties broken by total catches.
        """
        cases = ' '.join(
            f'WHEN p.rarity = {int(tier)} THEN {int(pts)}'
            for tier, pts in rarity_points.items()
        )
        rows = await self._fetch(
            f'SELECT c.user_id, '
            f'SUM(c.count * (CASE {cases} ELSE 0 END)) AS points, '
            f'SUM(c.count) AS total_catches, '
            f'COUNT(*) AS distinct_cards '
            f'FROM vocab_card_catches c '
            f'JOIN vocab_card_pool p ON p.card_id = c.card_id '
            f'GROUP BY c.user_id '
            f'ORDER BY points DESC, total_catches DESC LIMIT $1',
            limit,
        )
        return [dict(r) for r in rows]

    async def add_card(
        self,
        word_es: str,
        word_en: str,
        *,
        part_of_speech: str | None = None,
        gender: str | None = None,
        example_es: str | None = None,
        example_en: str | None = None,
        rarity: int = 1,
    ) -> int:
        """Insert a bidirectional card into the pool; returns the new card_id."""
        row = await self._fetchrow(
            'INSERT INTO vocab_card_pool '
            '(word_es, word_en, part_of_speech, gender, example_es, example_en, rarity) '
            'VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING card_id',
            word_es, word_en, part_of_speech, gender, example_es, example_en, rarity,
        )
        return row['card_id']

    async def count_pool_cards(self) -> int:
        """Number of active cards in the pool (for seeding/admin checks)."""
        n = await self._fetchval(
            'SELECT COUNT(*) FROM vocab_card_pool WHERE active = TRUE',
        )
        return n or 0
