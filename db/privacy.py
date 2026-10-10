"""Database mixin for self-serve user data deletion.

Every table holding per-user data must appear in exactly one of
``DELETED_TABLES`` or ``KEPT_TABLES``. ``tests/test_privacy.py`` parses the
schema and fails if a new user table is in neither, so the deletion command
can't silently fall behind the schema.
"""
import logging

from db import DatabaseMixin

logger = logging.getLogger(__name__)

# (table, SQL). $1 is the user ID. Order matters where foreign keys apply:
# wc_bets / wc_parlays reference wc_bet_wallets, so they go first.
_DELETES: list[tuple[str, str]] = [
    ("notes", "DELETE FROM notes WHERE user_id = $1"),
    ("vocab_notes", "DELETE FROM vocab_notes WHERE user_id = $1"),
    ("user_card_progress", "DELETE FROM user_card_progress WHERE user_id = $1"),
    ("user_conversation_limits", "DELETE FROM user_conversation_limits WHERE user_id = $1"),
    ("leaderboard_activity", "DELETE FROM leaderboard_activity WHERE user_id = $1"),
    # Banned members keep their row so the ban survives; see _ANONYMIZE.
    ("leaderboard_users", "DELETE FROM leaderboard_users WHERE user_id = $1 AND banned = FALSE"),
    ("league_round_winners", "DELETE FROM league_round_winners WHERE user_id = $1"),
    ("command_metrics", "DELETE FROM command_metrics WHERE user_id = $1"),
    ("interactions", "DELETE FROM interactions WHERE user_a = $1 OR user_b = $1"),
    ("crossword_scores", "DELETE FROM crossword_scores WHERE user_id = $1"),
    ("crossword_participants", "DELETE FROM crossword_participants WHERE user_id = $1"),
    ("dictation_scores", "DELETE FROM dictation_scores WHERE user_id = $1"),
    ("vocab_card_catches", "DELETE FROM vocab_card_catches WHERE user_id = $1"),
    ("ticket_subscriptions", "DELETE FROM ticket_subscriptions WHERE user_id = $1"),
    ("user_message_counts", "DELETE FROM user_message_counts WHERE user_id = $1"),
    ("user_activity", "DELETE FROM user_activity WHERE user_id = $1"),
    ("user_clock_prefs", "DELETE FROM user_clock_prefs WHERE user_id = $1"),
    ("spotify_optins", "DELETE FROM spotify_optins WHERE user_id = $1"),
    ("wc_predictions", "DELETE FROM wc_predictions WHERE user_id = $1"),
    ("wc_parlays", "DELETE FROM wc_parlays WHERE user_id = $1"),
    ("wc_bets", "DELETE FROM wc_bets WHERE user_id = $1"),
    ("wc_balance_log", "DELETE FROM wc_balance_log WHERE user_id = $1"),
    ("wc_bet_wallets", "DELETE FROM wc_bet_wallets WHERE user_id = $1"),
]

# Rows that stay but lose identifying data.
_ANONYMIZE: list[tuple[str, str]] = [
    ("crossword_word_events", "UPDATE crossword_word_events SET solved_by = NULL WHERE solved_by = $1"),
    (
        "leaderboard_users",
        "UPDATE leaderboard_users SET username = '', opted_in = FALSE "
        "WHERE user_id = $1 AND banned = TRUE",
    ),
]

# Owned by the Activity service (activity/backend/app/db.py). They may not
# exist if that service has never run against this database.
_ACTIVITY_DELETES: list[tuple[str, str]] = [
    ("game_results", "DELETE FROM game_results WHERE user_id = $1"),
    ("game_stats", "DELETE FROM game_stats WHERE user_id = $1"),
    ("activity_sessions", "DELETE FROM activity_sessions WHERE user_id = $1"),
    ("activity_pets", "DELETE FROM activity_pets WHERE user_id = $1"),
]

DELETED_TABLES: frozenset[str] = frozenset(
    t for t, _ in _DELETES + _ANONYMIZE + _ACTIVITY_DELETES
)

# Per-user tables deliberately kept, and why. Shown to users before they
# confirm, and listed in PRIVACY.md.
KEPT_TABLES: dict[str, str] = {
    "quote_optouts": "your choice not to be quoted",
    "quote_banned_users": "moderation record",
    "nogif_restrictions": "moderation record",
    "wc_bet_bans": "moderation record",
    "intro_exempt_users": "moderation record",
    "introductions": "moderation record",
    "exchange_posts": "anti-spam cooldown",
    "league_role_recipients": "champion role bookkeeping (removed at round end)",
    "tasks": "staff task board",
}


def _rowcount(status: str) -> int:
    """Parse the row count from an asyncpg status string like 'DELETE 3'."""
    tail = status.rsplit(" ", 1)[-1]
    return int(tail) if tail.isdigit() else 0


class PrivacyMixin(DatabaseMixin):
    """Deletes everything stored about one user, in a single transaction."""

    async def delete_user_data(self, user_id: int) -> int:
        """Delete or anonymize all of ``user_id``'s data. Returns rows affected."""
        total = 0
        async with self._pool().acquire() as conn, conn.transaction():
            for _table, sql in _DELETES + _ANONYMIZE:
                total += _rowcount(await conn.execute(sql, user_id))
            for table, sql in _ACTIVITY_DELETES:
                if await conn.fetchval("SELECT to_regclass($1)", f"public.{table}") is None:
                    continue
                total += _rowcount(await conn.execute(sql, user_id))
        logger.info("Deleted user data: %s rows affected", total)
        return total
