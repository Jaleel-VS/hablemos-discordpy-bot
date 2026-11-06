"""Which deploy owns the Discord session, and a log of instance lifecycle events."""
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from db import DatabaseMixin

INSTANCE_CLAIM_CHANNEL = "bot_instance_claimed"
EVENT_RETENTION_DAYS = 90


@dataclass(frozen=True)
class InstanceClaim:
    """The deploy that currently owns the bot session; version 0 means nobody has claimed it."""

    deploy_version: int
    instance_id: str
    claimed_at: datetime


NO_CLAIM = InstanceClaim(0, "", datetime.fromtimestamp(0, UTC))


class InstancesMixin(DatabaseMixin):
    async def active_instance(self) -> InstanceClaim:
        """Return the current claim, or NO_CLAIM if none was ever made."""
        row = await self._fetchrow(
            "SELECT deploy_version, instance_id, claimed_at FROM bot_instance WHERE singleton"
        )
        if row is None:
            return NO_CLAIM
        return InstanceClaim(row["deploy_version"], row["instance_id"], row["claimed_at"])

    async def claim_instance(self, deploy_version: int, instance_id: str) -> bool:
        """Take the session unless a newer deploy holds it; notify listeners on success.

        Equal versions may reclaim, so a restarted container of the current deploy keeps running.
        """
        async with self._pool().acquire() as conn, conn.transaction():
            claimed = await conn.fetchval(
                """
                INSERT INTO bot_instance (singleton, deploy_version, instance_id, claimed_at)
                VALUES (TRUE, $1, $2, NOW())
                ON CONFLICT (singleton) DO UPDATE
                SET deploy_version = EXCLUDED.deploy_version,
                    instance_id = EXCLUDED.instance_id,
                    claimed_at = EXCLUDED.claimed_at
                WHERE bot_instance.deploy_version <= EXCLUDED.deploy_version
                RETURNING TRUE
                """,
                deploy_version, instance_id,
            )
            if not claimed:
                return False
            await conn.execute(
                "SELECT pg_notify($1, $2)",
                INSTANCE_CLAIM_CHANNEL,
                json.dumps({"deploy_version": deploy_version, "instance_id": instance_id}),
            )
            await conn.execute(
                "DELETE FROM bot_instance_events WHERE created_at < NOW() - make_interval(days => $1)",
                EVENT_RETENTION_DAYS,
            )
            return True

    async def record_instance_event(
        self, deploy_version: int, instance_id: str, deploy_sha: str, event: str, detail: dict,
    ) -> None:
        """Append one lifecycle event (started, claimed, superseded, refused_stale, stopped)."""
        await self._execute(
            """
            INSERT INTO bot_instance_events (deploy_version, instance_id, deploy_sha, event, detail)
            VALUES ($1, $2, $3, $4, $5::jsonb)
            """,
            deploy_version, instance_id, deploy_sha, event, json.dumps(detail),
        )

    async def recent_instance_events(self, limit: int) -> list[dict]:
        """Newest lifecycle events first."""
        rows = await self._fetch(
            """
            SELECT deploy_version, instance_id, deploy_sha, event, detail, created_at
            FROM bot_instance_events ORDER BY id DESC LIMIT $1
            """,
            limit,
        )
        return [
            {**dict(row), "detail": json.loads(row["detail"]) if isinstance(row["detail"], str) else row["detail"]}
            for row in rows
        ]

    async def listen_instance_claims(
        self, callback: Callable[[dict], None],
    ) -> Callable[[], Awaitable[None]]:
        """Call ``callback`` with each claim payload; return a coroutine function that stops listening.

        LISTEN needs its own connection held for as long as we listen.
        """
        conn = await self._pool().acquire()

        def on_notify(_conn, _pid, _channel, payload: str) -> None:
            callback(json.loads(payload))

        await conn.add_listener(INSTANCE_CLAIM_CHANNEL, on_notify)

        async def stop() -> None:
            try:
                await conn.remove_listener(INSTANCE_CLAIM_CHANNEL, on_notify)
            finally:
                await self._pool().release(conn)

        return stop
