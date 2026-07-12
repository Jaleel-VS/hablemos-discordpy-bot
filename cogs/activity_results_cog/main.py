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
from discord.ext import commands, tasks

from base_cog import BaseCog
from cogs.utils.embeds import blue_embed

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

# Friendly labels for known game keys. The bot doesn't import the Activity's
# engine modules (separate service), so this is a small local map; an unknown
# key falls back to its raw value, capitalized.
_GAME_LABELS = {"wordle": "Wordle", "conjugation": "Conjugación"}


def _game_label(game_key: str) -> str:
    return _GAME_LABELS.get(game_key, game_key.capitalize())


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

    # ── owner stats command ─────────────────────────────────────────────────

    @commands.group(name="activity_stats", aliases=["astats"], invoke_without_command=True)
    @commands.is_owner()
    async def activity_stats(self, ctx: commands.Context) -> None:
        """Owner-only view of Activity persistence. Bare call: server totals."""
        await self._show_totals(ctx)

    @activity_stats.command(name="totals")
    async def activity_stats_totals(self, ctx: commands.Context) -> None:
        """Per-game counts: games, players, daily/free split, wins, pending."""
        await self._show_totals(ctx)

    @activity_stats.command(name="health")
    async def activity_stats_health(self, ctx: commands.Context) -> None:
        """Results-poster backlog: unposted daily rows + oldest pending age."""
        health = await self.bot.db.activity_pending_health()
        pending = health["pending"]
        oldest = health["oldest"]
        desc = (
            "✅ Sin resultados pendientes." if pending == 0
            else f"⏳ **{pending}** resultado(s) diario(s) sin publicar."
        )
        if oldest is not None:
            desc += f"\nMás antiguo: {discord.utils.format_dt(oldest, 'R')}"
        embed = blue_embed(desc)
        embed.title = "Actividad · estado del publicador"
        channel_state = (
            f"<#{ACTIVITY_RESULTS_CHANNEL_ID}>" if ACTIVITY_RESULTS_CHANNEL_ID > 0
            else "sin configurar (publicación desactivada)"
        )
        embed.add_field(name="Canal", value=channel_state, inline=False)
        await ctx.send(embed=embed)

    @activity_stats.command(name="streaks")
    async def activity_stats_streaks(self, ctx: commands.Context, game_key: str = "wordle") -> None:
        """Top daily streaks for a game (default: wordle)."""
        rows = await self.bot.db.activity_top_streaks(game_key=game_key, limit=10)
        if not rows:
            await ctx.send(embed=blue_embed(
                f"No hay rachas registradas para **{_game_label(game_key)}**."
            ))
            return
        lines = [
            f"{i}. <@{r['user_id']}> — racha máx **{r['max_streak']}** "
            f"(actual {r['current_streak']}, {r['wins']}/{r['games']})"
            for i, r in enumerate(rows, start=1)
        ]
        embed = blue_embed("\n".join(lines))
        embed.title = f"{_game_label(game_key)} · mejores rachas"
        await ctx.send(embed=embed)

    @activity_stats.command(name="user")
    async def activity_stats_user(
        self, ctx: commands.Context, member: discord.Member, game_key: str = "wordle",
    ) -> None:
        """One player's daily stats for a game (default: wordle)."""
        stats = await self.bot.db.activity_user_stats(game_key=game_key, user_id=member.id)
        if stats is None:
            await ctx.send(embed=blue_embed(
                f"{member.mention} no ha jugado **{_game_label(game_key)}** (diario)."
            ))
            return
        dist = _coerce_payload(stats["distribution"])
        dist_str = " · ".join(f"{k}: {v}" for k, v in sorted(dist.items())) or "—"
        embed = blue_embed(
            f"Partidas: **{stats['games']}** · Victorias: **{stats['wins']}**\n"
            f"Racha actual: **{stats['current_streak']}** · "
            f"Máxima: **{stats['max_streak']}**\n"
            f"Distribución: {dist_str}"
        )
        embed.title = f"{_game_label(game_key)} · {member.display_name}"
        await ctx.send(embed=embed)

    async def _show_totals(self, ctx: commands.Context) -> None:
        rows = await self.bot.db.activity_totals_by_game()
        if not rows:
            await ctx.send(embed=blue_embed(
                "No hay resultados de Actividad registrados todavía."
            ))
            return
        embed = blue_embed("")
        embed.title = "Actividad · totales por juego"
        total_games = 0
        for r in rows:
            total_games += r["games"]
            embed.add_field(
                name=_game_label(r["game_key"]),
                value=(
                    f"Partidas: **{r['games']}** ({r['daily']} diarias, "
                    f"{r['freeplay']} libres)\n"
                    f"Jugadores: **{r['players']}** · Victorias: **{r['wins']}**\n"
                    f"Diarias sin publicar: **{r['pending']}**"
                ),
                inline=False,
            )
        embed.description = f"**{total_games}** partidas en total."
        await ctx.send(embed=embed)


async def setup(bot: Hablemos):
    """Required setup fn for loading the cog."""
    await bot.add_cog(ActivityResultsCog(bot))
    logger.info("ActivityResultsCog loaded successfully")
