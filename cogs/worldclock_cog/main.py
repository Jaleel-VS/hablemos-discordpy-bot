"""World clock cog: a board of digital clocks for cities or people you choose.

``$clock`` (``$wc``) shows the board, ``$clock 20:00`` shows it at a planned
time, and ``add``/``remove``/``list``/``reset`` manage up to 12 saved clocks.
Each is also a ``/clock`` slash command, where the timezone autocompletes.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from base_cog import BaseCog
from cogs.utils.embeds import red_embed

from . import actions, zones
from .views import ClockManagerView, board_view

if TYPE_CHECKING:
    from hablemos import Hablemos

logger = logging.getLogger(__name__)

_RENDER_FAILED = "I couldn't draw your clocks. Try again in a moment."


class WorldClock(BaseCog):
    """Digital world clock board with per-member saved clocks."""

    @commands.hybrid_group(name="clock", aliases=["wc", "worldclock"], fallback="show")
    @commands.cooldown(1, 10, commands.BucketType.user)
    @app_commands.describe(at="Plan around a time in your timezone, e.g. 20:00 or 8pm")
    async def clock(self, ctx: commands.Context, *, at: str | None = None) -> None:
        """Show your world clock board. Usage: $clock [time]"""
        when = None
        if at is not None:
            when = zones.parse_clock_time(at)
            if when is None:
                await ctx.send(embed=red_embed("Use a time like `20:00`, `8pm` or `8:30am`."))
                return
        await ctx.defer()
        try:
            rendered = await actions.render_board(self.bot.db, ctx.author.id, when)
        except Exception:
            logger.exception("Failed to render world clock for %s", ctx.author.id)
            await ctx.send(embed=red_embed(_RENDER_FAILED))
            return
        await ctx.send(view=board_view(rendered), file=rendered.file())

    @clock.command(name="add")
    @commands.cooldown(5, 60, commands.BucketType.user)
    @app_commands.describe(name="Who or where, e.g. Emily", timezone="A city, IANA name or UTC offset")
    async def clock_add(self, ctx: commands.Context, name: str, *, timezone: str) -> None:
        """Add or update a clock. Usage: $clock add <name> <timezone> (quote names with spaces)"""
        outcome = await actions.add_clock(self.bot.db, ctx.author.id, name, timezone)
        reply = f"✅ {outcome.message}" if outcome.ok else f"❌ {outcome.message}"
        await ctx.send(reply, ephemeral=True)

    @clock_add.autocomplete("timezone")
    async def _timezone_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return [
            app_commands.Choice(name=display[:100], value=key)
            for display, key in zones.suggest_zones(current)
        ]

    @clock.command(name="remove")
    @commands.cooldown(5, 60, commands.BucketType.user)
    @app_commands.describe(name="The clock to remove")
    async def clock_remove(self, ctx: commands.Context, *, name: str) -> None:
        """Remove a clock by name. Usage: $clock remove <name>"""
        removed = await self.bot.db.remove_world_clock(ctx.author.id, name.strip())
        shown = discord.utils.escape_markdown(name.strip())
        reply = f"🗑️ Removed **{shown}**." if removed else f"❌ You have no clock called **{shown}**."
        await ctx.send(reply, ephemeral=True)

    @clock_remove.autocomplete("name")
    async def _label_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        clocks = await self.bot.db.get_world_clocks(interaction.user.id)
        return [
            app_commands.Choice(name=c.label, value=c.label)
            for c in clocks
            if current.lower() in c.label.lower()
        ][:25]

    @clock.command(name="list")
    @commands.cooldown(2, 30, commands.BucketType.user)
    async def clock_list(self, ctx: commands.Context) -> None:
        """List your clocks with buttons to add, edit and remove."""
        clocks = await self.bot.db.get_world_clocks(ctx.author.id)
        await ctx.send(view=ClockManagerView(self.bot, ctx.author.id, clocks), ephemeral=True)

    @clock.command(name="reset")
    @commands.cooldown(2, 60, commands.BucketType.user)
    async def clock_reset(self, ctx: commands.Context) -> None:
        """Delete all your clocks so $clock shows the default cities again."""
        removed = await self.bot.db.clear_world_clocks(ctx.author.id)
        await ctx.send(f"🗑️ Removed {removed} clock(s).", ephemeral=True)


async def setup(bot: Hablemos) -> None:
    """Required setup fn for loading the cog."""
    await bot.add_cog(WorldClock(bot))
    logger.info("WorldClock loaded successfully")
