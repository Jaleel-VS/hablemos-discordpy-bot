"""Owner command to delete a user's data on request (e.g. after they left)."""
from __future__ import annotations

from discord.ext import commands

from base_cog import BaseCog
from cogs.privacy_cog.views import ConfirmDeleteDataView, confirm_embed


class PrivacyAdmin(BaseCog):
    """Owner-only data deletion for requests made through moderators."""

    @commands.command(name="purgeuser")
    @commands.is_owner()
    async def purge_user(self, ctx: commands.Context, user_id: int) -> None:
        """Delete everything stored about a user ID. Usage: $purgeuser <user_id>"""
        view = ConfirmDeleteDataView(self.bot, ctx.author.id, user_id, confirm_label="Delete their data")
        view.message = await ctx.send(embed=confirm_embed(f"user `{user_id}`"), view=view)
