"""Admin commands for the World Cup predictions cog.

Owner-only prefix command group `$wcpredict` — set the deadline, record
the actual champion (which grades all predictions), reset state, and view
participation stats.
"""
from __future__ import annotations

import io
import logging
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING

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

if TYPE_CHECKING:
    from hablemos import Hablemos

logger = logging.getLogger(__name__)

ROLE_MENTION_RE = re.compile(r"<@&(\d+)>")

# Patterns for the embed descriptions produced by worldcup_cog/views.py
_RE_ASSIGNED = re.compile(
    r"\*\*(.+?)\*\* assigned themselves \*\*(.+?)\*\*\.",
)
_RE_SWITCHED = re.compile(
    r"\*\*(.+?)\*\* switched from \*\*(.+?)\*\* to \*\*(.+?)\*\*\.",
)
_RE_REMOVED = re.compile(
    r"\*\*(.+?)\*\* removed \*\*(.+?)\*\*\.",
)

# WC 2026 kickoff — predictions must be set *before* this to count as
# "from the first moment before the World Cup".
_WC_START = datetime(2026, 6, 11, tzinfo=UTC)
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

    def __init__(self, bot: Hablemos) -> None:
        super().__init__(bot)

    @commands.group(name="wcpredict", invoke_without_command=True)
    @commands.is_owner()
    async def wcpredict_admin(self, ctx: commands.Context) -> None:
        """Admin tools for the World Cup predictions feature."""
        await ctx.send(
            "Usage: `$wcpredict <setdeadline|cleardeadline|setwinner|clearwinner|stats|scanroles>`",
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

    # ---------- scan role log ----------

    @wcpredict_admin.command(name="scanroles")
    @commands.is_owner()
    async def scanroles(self, ctx: commands.Context, target_team: str = "Team Spain") -> None:
        """Scan #world-cup-log and report who had <target_team> from before the WC started.

        Reads all embed messages in the log channel, builds a per-user role
        history, then outputs three lists:
          • Loyal from day 1  — picked before WC start, never switched away
          • Changed but ended on target — was on target at end, but switched at some point
          • Picked after WC started — set target team only after Jun 11

        Usage: $wcpredict scanroles [team name]
        Default team: Team Spain
        """
        if ctx.guild is None:
            await ctx.send(embed=red_embed("Run this in the league guild."))
            return

        channel = ctx.guild.get_channel(WC_PREDICT_LOG_CHANNEL_ID)
        if not isinstance(channel, discord.TextChannel):
            await ctx.send(embed=red_embed(f"Can't find log channel `{WC_PREDICT_LOG_CHANNEL_ID}`."))
            return

        # Normalise target name for comparison (case-insensitive, strip whitespace)
        target = target_team.strip()
        if not target.lower().startswith("team "):
            target = f"Team {target}"

        status = await ctx.send(f"⏳ Scanning **{channel.name}** for `{target}` role history…")

        # --- fetch all messages (discord.py paginates internally) ---
        try:
            all_messages: list[discord.Message] = [
                msg async for msg in channel.history(limit=None, oldest_first=True)
            ]
        except discord.Forbidden:
            await status.edit(content="❌ No permission to read that channel.")
            return
        except discord.HTTPException:
            logger.exception("Failed to fetch history for channel %s", channel.id)
            await status.edit(content="❌ Failed to fetch messages.")
            return

        await status.edit(content=f"⏳ Fetched {len(all_messages)} messages, parsing…")

        # --- parse embeds into per-user event list ---
        # events[username] = list of (timestamp, team_name | None)
        #   None means "removed role entirely"
        events: dict[str, list[tuple[datetime, str | None]]] = {}

        for msg in all_messages:
            ts = msg.created_at  # always UTC-aware
            for embed in msg.embeds:
                desc = embed.description or ""

                m = _RE_ASSIGNED.search(desc)
                if m:
                    user, team = m.group(1), m.group(2)
                    events.setdefault(user, []).append((ts, team))
                    continue

                m = _RE_SWITCHED.search(desc)
                if m:
                    user, _from, to = m.group(1), m.group(2), m.group(3)
                    events.setdefault(user, []).append((ts, to))
                    continue

                m = _RE_REMOVED.search(desc)
                if m:
                    user, _team = m.group(1), m.group(2)
                    events.setdefault(user, []).append((ts, None))

        # --- classify users who currently end on target team ---
        loyal: list[str] = []          # picked target before WC, never left
        changed: list[str] = []        # on target now, but changed at some point
        late: list[str] = []           # first picked target after WC started

        for user, user_events in events.items():
            # Only care about users whose final state is the target team
            final_team = user_events[-1][1] if user_events else None
            if final_team != target:
                continue

            # Find the first time this user ever picked the target
            first_target_ts = next(
                (ts for ts, team in user_events if team == target),
                None,
            )
            if first_target_ts is None:
                continue

            # Did they ever leave the target after first picking it?
            first_target_idx = next(
                i for i, (ts, team) in enumerate(user_events) if team == target
            )
            ever_left = any(
                team != target
                for _, team in user_events[first_target_idx + 1:]
            )

            if first_target_ts >= _WC_START:
                late.append(f"{user} (first picked <t:{int(first_target_ts.timestamp())}:d>)")
            elif ever_left:
                changed.append(
                    f"{user} (first picked <t:{int(first_target_ts.timestamp())}:d>, strayed & returned)"
                )
            else:
                loyal.append(
                    f"{user} (since <t:{int(first_target_ts.timestamp())}:d>)"
                )

        # --- build output ---
        loyal_lines = [f"- {u}" for u in loyal] or ["- *(none)*"]
        changed_lines = [f"- {u}" for u in changed] or ["- *(none)*"]
        late_lines = [f"- {u}" for u in late] or ["- *(none)*"]
        lines: list[str] = [
            f"# {target} role history scan",
            f"Scanned **{len(all_messages)}** log messages · "
            f"**{len(events)}** unique users tracked\n",
            f"## ✅ Loyal from day 1 ({len(loyal)})",
            *loyal_lines,
            "",
            f"## ⚠️ On {target} now, but strayed at some point ({len(changed)})",
            *changed_lines,
            "",
            f"## 🕐 Picked {target} only after WC started ({len(late)})",
            *late_lines,
        ]

        content = "\n".join(lines).encode()
        filename = f"wc_scanroles_{target.replace(' ', '_').lower()}.md"
        report_file = discord.File(io.BytesIO(content), filename=filename)

        await status.edit(content=f"✅ Scan complete — {len(loyal)} loyal, {len(changed)} strayed, {len(late)} late.")
        await ctx.send(file=report_file)
        logger.info(
            "wcpredict scanroles run by %s: %d loyal, %d changed, %d late",
            ctx.author, len(loyal), len(changed), len(late),
        )

    # ---------- helpers ----------

    async def _log_grading(
        self,
        guild: discord.Guild,
        role: discord.Role,
        correct: int,
        total: int,
    ) -> None:
        channel = guild.get_channel(WC_PREDICT_LOG_CHANNEL_ID)
        if not isinstance(channel, discord.abc.Messageable):
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
