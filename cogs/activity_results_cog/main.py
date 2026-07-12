"""Posts finished Activity game results to a channel.

The Activity (embedded app) writes a row to ``game_results`` when a player
finishes a **daily** game (see ``activity/backend``). This cog polls for
unposted daily results and posts an emoji-grid card to a configured channel,
mentioning the player, then marks the row posted. It reuses the shared DB pool
and embed helpers; the bot stays gateway-only (no inbound HTTP).

The result ``payload`` is game-agnostic — every game's ``result_payload``
includes ``won``, ``summary`` (e.g. "Wordle #123 4/6"), and ``grid`` (the emoji
block) — so this cog posts any game's results without knowing the game.
"""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

import discord
from discord.ext import tasks

from base_cog import BaseCog

from .config import (
    ACTIVITY_RESULTS_BATCH,
    ACTIVITY_RESULTS_CHANNEL_ID,
    ACTIVITY_RESULTS_POLL_SECONDS,
)

if TYPE_CHECKING:
    from hablemos import Hablemos

logger = logging.getLogger(__name__)

_WIN_COLOR = 0x3AA394
_LOSS_COLOR = 0xED4245


def _coerce_payload(raw: Any) -> dict[str, Any]:
    """asyncpg returns JSONB as a str; normalize to a dict once, here."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}
    return {}


class ActivityResultsCog(BaseCog):
    """Background poster for finished Activity game results."""

    def __init__(self, bot: Hablemos):
        super().__init__(bot)
        self._logged_disabled = False
        self.poll_results.change_interval(seconds=ACTIVITY_RESULTS_POLL_SECONDS)
        self.poll_results.start()

    def cog_unload(self) -> None:
        self.poll_results.cancel()

    @tasks.loop(seconds=60)
    async def poll_results(self) -> None:
        """Post any unposted daily results, oldest first."""
        if ACTIVITY_RESULTS_CHANNEL_ID <= 0:
            if not self._logged_disabled:
                logger.info("ACTIVITY_RESULTS_CHANNEL_ID unset — result posting disabled")
                self._logged_disabled = True
            return

        channel = self.bot.get_channel(ACTIVITY_RESULTS_CHANNEL_ID)
        if not isinstance(channel, discord.abc.Messageable):
            logger.warning("Activity results channel %s not found/usable",
                           ACTIVITY_RESULTS_CHANNEL_ID)
            return

        rows = await self.bot.db.fetch_unposted_game_results(limit=ACTIVITY_RESULTS_BATCH)
        for row in rows:
            await self._post_one(channel, row)

    async def _post_one(self, channel: discord.abc.Messageable, row: Any) -> None:
        """Post a single result and mark it posted.

        Marks posted only after a successful send so a transient send failure
        is retried next tick. A malformed row is marked posted (and logged) so
        it can't wedge the queue forever.
        """
        result_id = row["id"]
        payload = _coerce_payload(row["payload"])
        if not payload:
            logger.warning("Activity result %s has unparseable payload; skipping", result_id)
            await self.bot.db.mark_game_result_posted(result_id)
            return

        embed = self._build_embed(user_id=row["user_id"], payload=payload)
        try:
            await channel.send(content=f"<@{row['user_id']}>", embed=embed)
        except (discord.Forbidden, discord.HTTPException) as exc:
            logger.warning("Failed to post activity result %s: %s", result_id, exc)
            return  # leave unposted; retried next tick

        await self.bot.db.mark_game_result_posted(result_id)

    @staticmethod
    def _build_embed(*, user_id: int, payload: dict[str, Any]) -> discord.Embed:
        won = bool(payload.get("won"))
        summary = payload.get("summary") or "Resultado"
        grid = payload.get("grid") or ""
        embed = discord.Embed(
            title=summary,
            description=grid or None,
            color=_WIN_COLOR if won else _LOSS_COLOR,
        )
        return embed

    @poll_results.before_loop
    async def _before_poll(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: Hablemos):
    """Required setup fn for loading the cog."""
    await bot.add_cog(ActivityResultsCog(bot))
    logger.info("ActivityResultsCog loaded successfully")
