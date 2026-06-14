"""Language Exchange cog.

A dedicated home for finding language-exchange partners, separate from
introductions. A persistent panel in the langex channel offers three
buttons: post/update your profile, find a mutual-match partner, and
delete your profile.

Profiles are stored in the shared ``exchange_posts`` table (reused from
the legacy introduce flow) so the two systems read the same data during
the transition. The persistent panel uses ``timeout=None`` with stable
``custom_id``s and is registered once via ``bot.add_view``.
"""
from __future__ import annotations

import logging

import discord
from discord.ext import commands

from base_cog import BaseCog
from cogs.utils.embeds import green_embed, red_embed

from .config import PANEL_CHANNEL_ID
from .i18n import t
from .views import LangExPanelView, _delete_message

logger = logging.getLogger(__name__)


class LangExCog(BaseCog):
    """Language-exchange partner finding and matchmaking."""

    def __init__(self, bot: commands.Bot):
        super().__init__(bot)
        # Register the persistent panel once so the buttons survive restarts.
        if not any(isinstance(v, LangExPanelView) for v in bot.persistent_views):
            bot.add_view(LangExPanelView(bot))

    @commands.command(name="langexpanel")
    @commands.has_permissions(manage_guild=True)
    async def post_panel(self, ctx: commands.Context):
        """Post the persistent language-exchange panel into the langex channel."""
        channel = self.bot.get_channel(PANEL_CHANNEL_ID)
        if not isinstance(channel, discord.abc.Messageable):
            await ctx.send(embed=red_embed("Panel channel is unavailable. Check `LANGEX_PANEL_CHANNEL_ID`."))
            return

        embed = discord.Embed(
            title=t("panel_title", "en"),
            description=f"{t('panel_body', 'en')}\n\n{t('panel_body', 'es')}",
            color=discord.Color.teal(),
        )
        try:
            await channel.send(embed=embed, view=LangExPanelView(self.bot))
        except discord.Forbidden:
            await ctx.send(embed=red_embed("I can't post in the panel channel. Check my permissions there."))
            return
        await ctx.send(embed=green_embed("Posted the language-exchange panel."))

    @commands.command(name="langexremove")
    @commands.has_permissions(manage_messages=True)
    async def remove_profile(self, ctx: commands.Context, user: discord.Member):
        """[Mod] Remove a user's language-exchange profile (message + record)."""
        post = await self.bot.db.get_exchange_post(user.id)
        if not post:
            await ctx.send(embed=red_embed(f"{user.mention} has no active profile."))
            return
        await _delete_message(self.bot, post.get("channel_id"), post.get("message_id"))
        await self.bot.db.delete_exchange_post(user.id)
        await ctx.send(embed=green_embed(f"Removed {user.mention}'s language-exchange profile."))


async def setup(bot: commands.Bot):
    await bot.add_cog(LangExCog(bot))
