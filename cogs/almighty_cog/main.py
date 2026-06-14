"""Almighty cog (working title) — relay form submissions between channels.

A persistent button in the trigger channel opens a form; submissions are
posted to the feed channel. Write in one channel, read in another.

The button survives restarts: ``TriggerView`` uses ``timeout=None`` with a
stable ``custom_id`` and is registered once via ``bot.add_view`` (guarded
against duplicate registration on cog reload).
"""
from __future__ import annotations

import logging

import discord
from discord.ext import commands

from base_cog import BaseCog
from cogs.utils.embeds import green_embed, red_embed

from .config import TRIGGER_CHANNEL_ID
from .views import TriggerView

logger = logging.getLogger(__name__)


class AlmightyCog(BaseCog):
    """Posts a persistent form button and relays submissions to a feed channel."""

    def __init__(self, bot: commands.Bot):
        super().__init__(bot)
        # Register the persistent view once so the button keeps working
        # across restarts. Guarded so cog reloads don't stack duplicates.
        if not any(isinstance(v, TriggerView) for v in bot.persistent_views):
            bot.add_view(TriggerView(bot))

    @commands.command(name="almightypanel")
    @commands.has_permissions(manage_guild=True)
    async def post_panel(self, ctx: commands.Context):
        """Post the persistent submission button into the trigger channel."""
        channel = self.bot.get_channel(TRIGGER_CHANNEL_ID)
        if not isinstance(channel, discord.abc.Messageable):
            await ctx.send(embed=red_embed("Trigger channel is unavailable. Check `ALMIGHTY_TRIGGER_CHANNEL_ID`."))
            return

        embed = discord.Embed(
            title="📝 Submit",
            description="Press the button below to open the form. Your submission will be posted to the feed channel.",
            color=discord.Color.blurple(),
        )
        try:
            await channel.send(embed=embed, view=TriggerView(self.bot))
        except discord.Forbidden:
            await ctx.send(embed=red_embed("I can't post in the trigger channel. Check my permissions there."))
            return
        await ctx.send(embed=green_embed("Posted the submission panel."))


async def setup(bot: commands.Bot):
    await bot.add_cog(AlmightyCog(bot))
