"""Privacy cog — lets members delete everything the bot stores about them."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from discord.ext import commands

from base_cog import BaseCog
from cogs.privacy_cog.views import ConfirmDeleteDataView, confirm_embed

if TYPE_CHECKING:
    from hablemos import Hablemos

logger = logging.getLogger(__name__)


class PrivacyCog(BaseCog):
    """Self-serve data deletion."""

    @commands.hybrid_command(name="deletemydata")
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def delete_my_data(self, ctx: commands.Context) -> None:
        """Permanently delete everything the bot stores about you."""
        view = ConfirmDeleteDataView(self.bot, ctx.author.id, ctx.author.id)
        view.message = await ctx.send(embed=confirm_embed("you"), view=view, ephemeral=True)


async def setup(bot: Hablemos) -> None:
    """Load the privacy cog and its admin commands."""
    from cogs.privacy_cog.admin import PrivacyAdmin

    await bot.add_cog(PrivacyCog(bot))
    await bot.add_cog(PrivacyAdmin(bot))
