"""Keep exactly one bot connected to Discord across Lightsail deploys.

Lightsail starts the new container before stopping the old one, and Discord
delivers every event to each session logged in with the token, so for a while
both bots answer commands and every message listener counts twice.

Each Lightsail deployment carries ``DEPLOY_VERSION``, its creation time. On gateway
connect the bot claims the session in Postgres unless a newer deploy holds it.
Older instances hear the claim over LISTEN/NOTIFY, or on the next poll if they
missed it, and shut down. A container that starts after a newer deploy has
claimed refuses to log in at all.
"""
from __future__ import annotations

import asyncio
import logging
import socket
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import uuid4

import asyncpg

from db import Database
from db.instances import InstanceClaim

logger = logging.getLogger(__name__)

POLL_SECONDS = 10.0
DB_ERRORS = (asyncpg.PostgresError, asyncpg.InterfaceError, OSError)


class StaleDeployment(Exception):
    """A newer deploy owns the session; this instance must not log in."""


class InstanceGuard:
    """Claims the Discord session for this deploy and steps aside for newer ones."""

    def __init__(
        self,
        db: Database,
        deploy_version: int,
        deploy_sha: str,
        on_superseded: Callable[[], Awaitable[None]],
        *,
        poll_seconds: float = POLL_SECONDS,
    ) -> None:
        self.db = db
        self.deploy_version = deploy_version
        self.deploy_sha = deploy_sha
        self.instance_id = f"{socket.gethostname()}-{uuid4().hex[:6]}"
        self.enabled = deploy_version > 0
        self.superseded = False
        self._on_superseded = on_superseded
        self._poll_seconds = poll_seconds
        self._claimed = False
        self._wants_claim = False
        self._tasks: set[asyncio.Task] = set()
        self._claims = 0
        self._started = time.monotonic()
        self._poll_task: asyncio.Task | None = None
        self._stop_listening: Callable[[], Awaitable[None]] | None = None

    async def start(self) -> None:
        """Refuse to run behind a newer deploy, then start watching for one."""
        if not self.enabled:
            logger.warning("DEPLOY_VERSION is not set; the duplicate-instance guard is off")
            return
        logger.info(
            "Instance %s starting for deploy v%s (%s)",
            self.instance_id, self.deploy_version, self.deploy_sha,
        )
        active = await self.db.active_instance()
        await self._record("started", {"active_version": active.deploy_version})
        if active.deploy_version > self.deploy_version:
            logger.warning(
                "Deploy v%s already owns the bot session; v%s will not log in",
                active.deploy_version, self.deploy_version,
            )
            await self._record("refused_stale", {"active_version": active.deploy_version})
            raise StaleDeployment(active.deploy_version)
        self._stop_listening = await self.db.listen_instance_claims(self._on_notify)
        self._poll_task = asyncio.create_task(self._poll(), name="instance-guard-poll")

    async def claim(self) -> None:
        """Take the session on gateway connect (called again on every reconnect).

        A failed attempt is retried by the poll loop.
        """
        if not self.enabled or self.superseded:
            return
        self._wants_claim = True
        try:
            previous = await self.db.active_instance()
            claimed = await self.db.claim_instance(self.deploy_version, self.instance_id)
            active = previous if claimed else await self.db.active_instance()
        except DB_ERRORS:
            self._claimed = False
            logger.warning("Claiming the bot session failed; retrying on the next poll", exc_info=True)
            return
        if not claimed:
            await self._supersede("claim_rejected", active)
            return
        self._claimed = True
        self._claims += 1
        logger.info(
            "Deploy v%s claimed the bot session (previous: v%s %s)",
            self.deploy_version, previous.deploy_version, previous.instance_id or "none",
        )
        await self._record("claimed", {
            "claims": self._claims,
            "previous_version": previous.deploy_version,
            "previous_instance": previous.instance_id,
            "seconds_since_start": round(time.monotonic() - self._started, 1),
        })

    async def stop(self) -> None:
        """Stop watching and record how long this instance ran."""
        if self._poll_task is None:
            return
        self._poll_task.cancel()
        self._poll_task = None
        if self._stop_listening is not None:
            try:
                await self._stop_listening()
            except DB_ERRORS:
                logger.warning("Failed to stop the instance-claim listener", exc_info=True)
            self._stop_listening = None
        uptime = round(time.monotonic() - self._started, 1)
        logger.info("Instance %s stopping after %ss", self.instance_id, uptime)
        await self._record("stopped", {"uptime_seconds": uptime, "superseded": self.superseded})

    def _on_notify(self, payload: dict) -> None:
        if payload.get("deploy_version", 0) > self.deploy_version:
            task = asyncio.get_running_loop().create_task(self._supersede_from_db("notify"))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def _poll(self) -> None:
        while not self.superseded:
            await asyncio.sleep(self._poll_seconds)
            try:
                active = await self.db.active_instance()
                if active.deploy_version > self.deploy_version:
                    await self._supersede("poll", active)
                elif self._wants_claim and not self._claimed:
                    await self.claim()
            except DB_ERRORS:
                logger.warning("Instance guard poll failed", exc_info=True)

    async def _supersede_from_db(self, via: str) -> None:
        try:
            active = await self.db.active_instance()
        except DB_ERRORS:
            logger.warning("Could not read the active instance after a claim notice", exc_info=True)
            return
        if active.deploy_version > self.deploy_version:
            await self._supersede(via, active)

    async def _supersede(self, via: str, active: InstanceClaim) -> None:
        if self.superseded:
            return
        self.superseded = True
        overlap = (datetime.now(UTC) - active.claimed_at).total_seconds()
        logger.warning(
            "Deploy v%s (%s) took over the bot session; v%s shutting down (%s, %.1fs after the claim)",
            active.deploy_version, active.instance_id, self.deploy_version, via, overlap,
        )
        await self._record("superseded", {
            "via": via,
            "newer_version": active.deploy_version,
            "newer_instance": active.instance_id,
            "overlap_seconds": round(overlap, 2),
        })
        # Shut down from a separate task: stop() cancels the poll task, which may be the caller.
        task = asyncio.get_running_loop().create_task(self._on_superseded())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _record(self, event: str, detail: dict) -> None:
        try:
            await self.db.record_instance_event(
                self.deploy_version, self.instance_id, self.deploy_sha, event, detail,
            )
        except DB_ERRORS:
            logger.warning("Failed to record instance event %s", event, exc_info=True)
