"""Admin commands for the World Cup predictions cog.

Owner-only prefix command group `$wcpredict` — set the deadline, record
the actual champion (which grades all predictions), reset state, and view
participation stats.
"""
from __future__ import annotations

import csv
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
        # Key: "uid:<user_id>" when the footer has one (new logs), else the
        # display username (old logs). Using the ID eliminates rename splits.
        # events[key] = list of (timestamp, team_name | None, label)
        #   team_name None means "removed role entirely"
        #   label is the human-readable name for the report
        events: dict[str, list[tuple[datetime, str | None]]] = {}
        key_to_label: dict[str, str] = {}

        _RE_FOOTER_UID = re.compile(r"^user_id:(\d+)$")

        for msg in all_messages:
            ts = msg.created_at  # always UTC-aware
            for embed in msg.embeds:
                desc = embed.description or ""

                # Prefer footer user_id as the stable key; fall back to username
                footer_text = embed.footer.text if embed.footer else None
                uid_match = _RE_FOOTER_UID.match(footer_text) if footer_text else None

                m = _RE_ASSIGNED.search(desc)
                if m:
                    username, team = m.group(1), m.group(2)
                    key = f"uid:{uid_match.group(1)}" if uid_match else username
                    key_to_label[key] = username
                    events.setdefault(key, []).append((ts, team))
                    continue

                m = _RE_SWITCHED.search(desc)
                if m:
                    username, _from, to = m.group(1), m.group(2), m.group(3)
                    key = f"uid:{uid_match.group(1)}" if uid_match else username
                    key_to_label[key] = username
                    events.setdefault(key, []).append((ts, to))
                    continue

                m = _RE_REMOVED.search(desc)
                if m:
                    username, _team = m.group(1), m.group(2)
                    key = f"uid:{uid_match.group(1)}" if uid_match else username
                    key_to_label[key] = username
                    events.setdefault(key, []).append((ts, None))

        # --- build flat CSV audit table (all users who ever touched target) ---
        # Columns: verdict, user_id, names_seen, first_pick, final_team, events

        csv_buf = io.StringIO()
        writer = csv.writer(csv_buf)
        writer.writerow(["verdict", "user_id", "names_seen", "first_pick", "final_team", "events"])

        for key, user_events in sorted(events.items(), key=lambda kv: kv[1][0][0]):
            final_team = user_events[-1][1] or "removed"

            # Only rows that ever touched the target team
            if not any(team == target for _, team in user_events):
                continue

            user_id = key[4:] if key.startswith("uid:") else ""
            label = key_to_label.get(key, key)

            first_target_ts = next(ts for ts, team in user_events if team == target)
            first_target_idx = next(i for i, (ts, team) in enumerate(user_events) if team == target)
            ever_left = any(team != target for _, team in user_events[first_target_idx + 1:])

            if final_team != target:
                verdict = "LEFT"
            elif first_target_ts >= _WC_START:
                verdict = "LATE"
            elif ever_left:
                verdict = "STRAYED"
            else:
                verdict = "LOYAL"

            event_chain = " → ".join(
                f"{team or 'removed'} ({ts.strftime('%b %d')})"
                for ts, team in user_events
            )

            writer.writerow([
                verdict,
                user_id,
                label,
                first_target_ts.strftime("%Y-%m-%d"),
                final_team,
                event_chain,
            ])

        csv_content = csv_buf.getvalue().encode()
        filename = f"wc_audit_{target.replace(' ', '_').lower()}.csv"
        report_file = discord.File(io.BytesIO(csv_content), filename=filename)

        # Quick summary counts for the status message
        rows_preview = [r for r in csv.DictReader(io.StringIO(csv_buf.getvalue()))]
        counts = {}
        for r in rows_preview:
            counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1

        summary = "  ".join(f"{v}:{counts.get(v, 0)}" for v in ("LOYAL", "STRAYED", "LATE", "LEFT"))
        await status.edit(content=f"✅ {len(rows_preview)} users touched `{target}` — {summary}")
        await ctx.send(file=report_file)
        logger.info("wcpredict scanroles by %s: %s", ctx.author, summary)

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
