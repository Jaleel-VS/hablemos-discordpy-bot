"""Automod watch cog — alert staff when AutoMod flags spike in a channel.

Listens for `on_automod_action` events. When the same channel accumulates
≥ threshold flags within window_seconds, fires an alert embed to the
configured staff channel with jump links to every flagged message and
their corresponding watch-log entries.
"""
from __future__ import annotations

import logging
from collections import defaultdict, deque
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from base_cog import BaseCog
from cogs.utils.embeds import green_embed, red_embed
from db.automod_watch import (
    KEY_ALERT_CHANNEL,
    KEY_LOG_CHANNEL,
    KEY_THRESHOLD,
    KEY_WINDOW,
)

from .config import DEFAULT_ALERT_CHANNEL_ID, DEFAULT_LOG_CHANNEL_ID

if TYPE_CHECKING:
    from hablemos import Hablemos

logger = logging.getLogger(__name__)


class _FlagEvent:
    """One AutoMod flag occurrence, held in the sliding window."""

    __slots__ = ("alert_msg_id", "channel_id", "keyword", "message_id", "ts", "user_id")

    def __init__(
        self,
        ts: datetime,
        keyword: str | None,
        channel_id: int,
        message_id: int | None,
        user_id: int,
        alert_msg_id: int | None,
    ) -> None:
        self.ts = ts
        self.keyword = keyword
        self.channel_id = channel_id
        self.message_id = message_id
        self.user_id = user_id
        self.alert_msg_id = alert_msg_id


class AutomodWatch(BaseCog):
    """Watch AutoMod flag events and alert staff when they spike."""

    def __init__(self, bot: Hablemos) -> None:
        super().__init__(bot)
        # channel_id -> deque[_FlagEvent]  (sliding window, oldest first)
        self._windows: dict[int, deque[_FlagEvent]] = defaultdict(deque)

    # ── helpers ──────────────────────────────────────────────────────────────

    async def _get_config(self) -> dict:
        cfg = await self.bot.db.get_automod_watch_config()
        if not cfg["log_channel_id"] and DEFAULT_LOG_CHANNEL_ID:
            cfg["log_channel_id"] = DEFAULT_LOG_CHANNEL_ID
        if not cfg["alert_channel_id"] and DEFAULT_ALERT_CHANNEL_ID:
            cfg["alert_channel_id"] = DEFAULT_ALERT_CHANNEL_ID
        return cfg

    def _jump(self, guild_id: int, channel_id: int, message_id: int) -> str:
        return f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"

    def _prune(self, window: deque[_FlagEvent], window_seconds: int) -> None:
        cutoff = datetime.now(UTC).timestamp() - window_seconds
        while window and window[0].ts.timestamp() < cutoff:
            window.popleft()

    async def _fire_alert(
        self,
        guild: discord.Guild,
        alert_channel_id: int,
        log_channel_id: int,
        source_channel_id: int,
        events: list[_FlagEvent],
        threshold: int,
        window_seconds: int,
    ) -> None:
        alert_channel = guild.get_channel(alert_channel_id)
        if not isinstance(alert_channel, discord.abc.Messageable):
            logger.warning(
                "automod_watch: alert channel %s not found in guild %s",
                alert_channel_id, guild.id,
            )
            return

        minutes = window_seconds // 60
        keywords = ", ".join(
            f"`{e.keyword}`" for e in events if e.keyword
        ) or "*(unknown)*"

        embed = discord.Embed(
            title="⚠️ AutoMod spike detected",
            description=(
                f"**{len(events)}** flags in <#{source_channel_id}> "
                f"within the last **{minutes} min** (threshold: {threshold}).\n"
                f"Keywords: {keywords}"
            ),
            color=discord.Color.red(),
            timestamp=datetime.now(UTC),
        )

        for i, event in enumerate(events, 1):
            parts = []
            # Link to the original triggering message
            if event.message_id:
                parts.append(
                    f"[Original message]({self._jump(guild.id, event.channel_id, event.message_id)})"
                )
            # Link to the AutoMod alert in the watch-log channel
            if event.alert_msg_id and log_channel_id:
                parts.append(
                    f"[Watch-log entry]({self._jump(guild.id, log_channel_id, event.alert_msg_id)})"
                )
            user = guild.get_member(event.user_id)
            user_str = user.mention if user else f"`{event.user_id}`"
            kw = f"`{event.keyword}`" if event.keyword else "*(unknown)*"
            embed.add_field(
                name=f"Flag {i} — {kw}",
                value=f"{user_str}  {' · '.join(parts) or '*(no links)*'}",
                inline=False,
            )

        try:
            await alert_channel.send(embed=embed)
            logger.info(
                "automod_watch: fired alert for channel %s (%d flags)",
                source_channel_id, len(events),
            )
        except (discord.Forbidden, discord.HTTPException):
            logger.exception(
                "automod_watch: failed to send alert to channel %s", alert_channel_id
            )

    # ── listener ─────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_automod_action(self, execution: discord.AutoModAction) -> None:
        """Track AutoMod flag events and fire staff alerts on spikes."""
        try:
            cfg = await self._get_config()
        except Exception:
            logger.exception("automod_watch: failed to load config")
            return

        log_channel_id: int = cfg["log_channel_id"] or 0
        alert_channel_id: int = cfg["alert_channel_id"] or 0
        threshold: int = cfg["threshold"]
        window_seconds: int = cfg["window_seconds"]

        if not alert_channel_id:
            return  # not configured — silently skip

        # channel_id is Optional in the discord.py type stubs; a flag with no
        # channel is not useful to us — skip rather than risk a KeyError.
        if execution.channel_id is None:
            return

        guild = self.bot.get_guild(execution.guild_id)
        if guild is None:
            return

        channel_id: int = execution.channel_id

        event = _FlagEvent(
            ts=datetime.now(UTC),
            keyword=execution.matched_keyword,
            channel_id=channel_id,
            message_id=execution.message_id,
            user_id=execution.user_id,
            alert_msg_id=execution.alert_system_message_id,
        )

        window = self._windows[channel_id]
        self._prune(window, window_seconds)
        window.append(event)

        if len(window) >= threshold:
            events = list(window)
            window.clear()
            await self._fire_alert(
                guild,
                alert_channel_id,
                log_channel_id,
                channel_id,
                events,
                threshold,
                window_seconds,
            )

    # ── admin commands ────────────────────────────────────────────────────────

    @commands.group(name="automodwatch", aliases=["amwatch"], invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def automodwatch(self, ctx: commands.Context) -> None:
        """Manage the AutoMod spike-alert feature."""
        await ctx.invoke(self.status)

    @automodwatch.command(name="setlogchannel")
    @commands.has_permissions(manage_guild=True)
    async def setlogchannel(self, ctx: commands.Context) -> None:
        """Set the channel where AutoMod posts its flag messages.

        Usage: $automodwatch setlogchannel #channel
        """
        if not ctx.message.channel_mentions:
            await ctx.send(embed=red_embed("Usage: `$automodwatch setlogchannel #channel`"))
            return
        channel = ctx.message.channel_mentions[0]
        await self.bot.db.set_bot_setting(KEY_LOG_CHANNEL, channel.id)
        await ctx.send(embed=green_embed(f"AutoMod log channel set to {channel.mention} ✅"))
        logger.info("automod_watch log channel set to %s by %s", channel.id, ctx.author)

    @automodwatch.command(name="setalertchannel")
    @commands.has_permissions(manage_guild=True)
    async def setalertchannel(self, ctx: commands.Context) -> None:
        """Set the staff channel to receive spike alerts.

        Usage: $automodwatch setalertchannel #channel
        """
        if not ctx.message.channel_mentions:
            await ctx.send(embed=red_embed("Usage: `$automodwatch setalertchannel #channel`"))
            return
        channel = ctx.message.channel_mentions[0]
        await self.bot.db.set_bot_setting(KEY_ALERT_CHANNEL, channel.id)
        await ctx.send(embed=green_embed(f"Alert channel set to {channel.mention} ✅"))
        logger.info("automod_watch alert channel set to %s by %s", channel.id, ctx.author)

    @automodwatch.command(name="setthreshold")
    @commands.has_permissions(manage_guild=True)
    async def setthreshold(self, ctx: commands.Context, value: int) -> None:
        """Set how many flags in the window trigger an alert (default 2).

        Usage: $automodwatch setthreshold <n>
        """
        if value < 1:
            await ctx.send(embed=red_embed("Threshold must be at least 1."))
            return
        await self.bot.db.set_bot_setting(KEY_THRESHOLD, value)
        await ctx.send(embed=green_embed(f"Threshold set to **{value}** flags ✅"))
        logger.info("automod_watch threshold set to %s by %s", value, ctx.author)

    @automodwatch.command(name="setwindow")
    @commands.has_permissions(manage_guild=True)
    async def setwindow(self, ctx: commands.Context, seconds: int) -> None:
        """Set the sliding window size in seconds (default 300 = 5 min).

        Usage: $automodwatch setwindow <seconds>
        """
        if seconds < 10:
            await ctx.send(embed=red_embed("Window must be at least 10 seconds."))
            return
        await self.bot.db.set_bot_setting(KEY_WINDOW, seconds)
        minutes = seconds / 60
        await ctx.send(embed=green_embed(f"Window set to **{seconds}s** ({minutes:.1f} min) ✅"))
        logger.info("automod_watch window set to %ss by %s", seconds, ctx.author)

    @automodwatch.command(name="status")
    @commands.has_permissions(manage_guild=True)
    async def status(self, ctx: commands.Context) -> None:
        """Show current automod-watch configuration."""
        cfg = await self._get_config()
        log_id = cfg["log_channel_id"]
        alert_id = cfg["alert_channel_id"]
        embed = discord.Embed(title="AutoMod Watch — Status", color=discord.Color.blurple())
        embed.add_field(
            name="AutoMod log channel",
            value=f"<#{log_id}>" if log_id else "⚠️ Not set (`$automodwatch setlogchannel`)",
            inline=False,
        )
        embed.add_field(
            name="Alert channel",
            value=f"<#{alert_id}>" if alert_id else "⚠️ Not set (`$automodwatch setalertchannel`)",
            inline=False,
        )
        embed.add_field(name="Threshold", value=f"{cfg['threshold']} flags", inline=True)
        embed.add_field(
            name="Window",
            value=f"{cfg['window_seconds']}s ({cfg['window_seconds'] // 60} min)",
            inline=True,
        )
        await ctx.send(embed=embed)


async def setup(bot: Hablemos) -> None:
    await bot.add_cog(AutomodWatch(bot))
