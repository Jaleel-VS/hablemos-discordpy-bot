"""Admin commands for the World Cup predictions cog.

Owner-only prefix command group `$wcpredict` — set the deadline, record
the actual champion (which grades all predictions), reset state, and view
participation stats.
"""
import logging
import re
from datetime import UTC, datetime

import discord
from discord.ext import commands

from base_cog import BaseCog
from cogs.utils.embeds import blue_embed, green_embed, red_embed

from .config import (
    SETTING_KEY_DEADLINE,
    SETTING_KEY_WINNER,
    WC_PREDICT_LOG_CHANNEL_ID,
)
from .scoring import score_prediction

logger = logging.getLogger(__name__)

ROLE_MENTION_RE = re.compile(r"<@&(\d+)>")


def _parse_deadline(raw: str) -> int | None:
    """Parse a deadline argument into a Unix epoch.

    Accepts either a raw integer epoch (seconds) or an ISO-8601 string
    (e.g. ``2026-06-11T18:00:00Z`` or ``2026-06-11 18:00``). Naive
    datetimes are interpreted as UTC. Returns None on parse failure.
    """
    raw = raw.strip()
    if raw.isdigit():
        return int(raw)
    iso = raw.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return int(dt.timestamp())


def _resolve_team_role(guild: discord.Guild, raw: str) -> discord.Role | None:
    """Resolve a `Team X` role from a mention, ID, or name fragment."""
    raw = raw.strip()
    mention = ROLE_MENTION_RE.fullmatch(raw)
    if mention:
        return guild.get_role(int(mention.group(1)))
    if raw.isdigit():
        return guild.get_role(int(raw))
    # Match by name. Accept "Team X" or just "X".
    needle = raw.lower()
    if not needle.startswith("team "):
        needle = f"team {needle}"
    for role in guild.roles:
        if role.name.lower() == needle:
            return role
    return None


class WCPredictAdmin(BaseCog):
    """Owner-only `$wcpredict` admin group."""

    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(bot)

    @commands.group(name="wcpredict", invoke_without_command=True)
    @commands.is_owner()
    async def wcpredict_admin(self, ctx: commands.Context) -> None:
        """Admin tools for the World Cup predictions feature."""
        await ctx.send(
            "Usage: `$wcpredict <setdeadline|cleardeadline|setwinner|clearwinner|stats>`",
        )

    # ---------- deadline ----------

    @wcpredict_admin.command(name="setdeadline")
    @commands.is_owner()
    async def setdeadline(self, ctx: commands.Context, *, when: str) -> None:
        """Set the prediction lock deadline.

        Examples:
            $wcpredict setdeadline 2026-06-11T18:00:00Z
            $wcpredict setdeadline 1781020800
        """
        ts = _parse_deadline(when)
        if ts is None:
            await ctx.send(
                embed=red_embed(
                    "Couldn't parse that timestamp. Use ISO-8601 "
                    "(e.g. `2026-06-11T18:00:00Z`) or a Unix epoch.",
                ),
            )
            return
        await self.bot.db.set_bot_setting(SETTING_KEY_DEADLINE, ts)
        await ctx.send(
            embed=green_embed(
                f"Deadline set to <t:{ts}:F> (<t:{ts}:R>).",
            ),
        )
        logger.info("wcpredict deadline set to %s by %s", ts, ctx.author)

    @wcpredict_admin.command(name="cleardeadline")
    @commands.is_owner()
    async def cleardeadline(self, ctx: commands.Context) -> None:
        """Remove the deadline (predictions become editable again)."""
        await self.bot.db.set_bot_setting(SETTING_KEY_DEADLINE, 0)
        await ctx.send(embed=green_embed("Deadline cleared."))
        logger.info("wcpredict deadline cleared by %s", ctx.author)

    # ---------- winner ----------

    @wcpredict_admin.command(name="setwinner")
    @commands.is_owner()
    async def setwinner(self, ctx: commands.Context, *, team: str) -> None:
        """Record the actual World Cup champion and grade predictions.

        `team` can be a role mention, role ID, or team name (e.g. `Brazil`
        or `Team Brazil`).
        """
        if ctx.guild is None:
            await ctx.send(embed=red_embed("Run this in the league guild."))
            return

        role = _resolve_team_role(ctx.guild, team)
        if role is None or not role.name.startswith("Team "):
            await ctx.send(
                embed=red_embed(
                    "Couldn't resolve that to a `Team X` role. "
                    "Try a mention, role ID, or the country name.",
                ),
            )
            return

        await self.bot.db.set_bot_setting(SETTING_KEY_WINNER, role.id)

        rows = await self.bot.db.get_all_wc_predictions(ctx.guild.id)
        correct = sum(1 for r in rows if score_prediction(r["team_role_id"], role.id) > 0)

        await ctx.send(
            embed=green_embed(
                f"🏆 Champion set to **{role.name}**. "
                f"{correct}/{len(rows)} prediction{'s' if len(rows) != 1 else ''} were correct.",
            ),
        )
        logger.info(
            "wcpredict winner set to role_id=%s by %s (%d/%d correct)",
            role.id, ctx.author, correct, len(rows),
        )
        await self._log_grading(ctx.guild, role, correct, len(rows))

    @wcpredict_admin.command(name="clearwinner")
    @commands.is_owner()
    async def clearwinner(self, ctx: commands.Context) -> None:
        """Reset the recorded champion (un-grade)."""
        await self.bot.db.set_bot_setting(SETTING_KEY_WINNER, 0)
        await ctx.send(embed=green_embed("Champion cleared. Predictions are un-graded."))
        logger.info("wcpredict winner cleared by %s", ctx.author)

    # ---------- stats ----------

    @wcpredict_admin.command(name="stats")
    @commands.is_owner()
    async def stats(self, ctx: commands.Context) -> None:
        """Show participation totals and per-team distribution."""
        if ctx.guild is None:
            await ctx.send(embed=red_embed("Run this in the league guild."))
            return

        total = await self.bot.db.count_wc_predictions(ctx.guild.id)
        if total == 0:
            await ctx.send(embed=blue_embed("No predictions stored yet."))
            return

        dist = await self.bot.db.wc_prediction_team_distribution(ctx.guild.id)
        lines = [f"**{r['team_name']}** — {r['picks']}" for r in dist]
        embed = discord.Embed(
            title="World Cup prediction stats",
            description="\n".join(lines),
            color=discord.Color.blurple(),
        )
        embed.set_footer(text=f"{total} total prediction(s)")
        await ctx.send(embed=embed)

    # ---------- helpers ----------

    async def _log_grading(
        self,
        guild: discord.Guild,
        role: discord.Role,
        correct: int,
        total: int,
    ) -> None:
        channel = guild.get_channel(WC_PREDICT_LOG_CHANNEL_ID)
        if channel is None:
            logger.warning(
                "wcpredict log channel %s not found in guild %s",
                WC_PREDICT_LOG_CHANNEL_ID, guild.id,
            )
            return
        embed = discord.Embed(
            title="🏆 World Cup champion set",
            description=(
                f"Champion: **{role.name}**\n"
                f"{correct} of {total} prediction{'s' if total != 1 else ''} were correct."
            ),
            color=role.color or discord.Color.gold(),
        )
        try:
            await channel.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException) as exc:
            logger.error(
                "Failed to send grading log to channel %s: %s",
                WC_PREDICT_LOG_CHANNEL_ID, exc,
            )
