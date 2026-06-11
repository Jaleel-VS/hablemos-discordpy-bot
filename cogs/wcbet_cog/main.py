"""World Cup betting cog — `$wcbet` opens a personal ephemeral betting panel.

Group-stage match betting with virtual coins: opt in once for a starting
balance, pick today's match + outcome + stake from a Components V2
stepper, and get paid 1.5x on correct bets. Settlement is manual via the
owner-only `$wcbetadmin` group (see `admin.py`).
"""
import logging

from discord.ext import commands

from base_cog import BaseCog

from .admin import WCBetAdmin
from .views import OpenBetPanelView

logger = logging.getLogger(__name__)


class WCBet(BaseCog):
    """`$wcbet` — World Cup match betting with virtual coins."""

    async def _send_prompt(self, ctx: commands.Context) -> None:
        """Send the public button prompt that opens a personal panel."""
        view = OpenBetPanelView(self.bot)
        prompt = await ctx.send(
            "🎰 **World Cup betting** — click to open your personal panel.",
            view=view,
        )
        view.prompt_message = prompt

    # Public entrypoint — enable once testing is complete (see $wcbettest):
    # @commands.command(name="wcbet")
    # @commands.cooldown(1, 5, commands.BucketType.user)
    # @commands.guild_only()
    # async def wcbet(self, ctx: commands.Context) -> None:
    #     """Open the World Cup betting panel."""
    #     await self._send_prompt(ctx)

    @commands.command(name="wcbettest")
    @commands.is_owner()
    @commands.guild_only()
    async def wcbettest(self, ctx: commands.Context) -> None:
        """Open the World Cup betting panel (owner-only test entrypoint)."""
        await self._send_prompt(ctx)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WCBet(bot))
    await bot.add_cog(WCBetAdmin(bot))
