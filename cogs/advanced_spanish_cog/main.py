"""Unlisted advanced Spanish vocabulary command."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from discord.ext import commands

from cogs.utils.vocabulary import VocabularyCog

if TYPE_CHECKING:
    from hablemos import Hablemos

DATA_DIR = Path(__file__).resolve().parent / "data"


class AdvancedSpanish(VocabularyCog):
    """An unlisted collection of precise Spanish vocabulary and usage examples."""

    def __init__(self, bot: Hablemos) -> None:
        super().__init__(bot, DATA_DIR, "es")

    @commands.command(name="c", hidden=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def vocabulary(self, ctx: commands.Context, *, query: str = "") -> None:
        """Browse advanced Spanish; optionally find a term, e.g. $c explayarse."""
        await self.show_card(ctx, query)


async def setup(bot: Hablemos) -> None:
    """Load the hidden Spanish vocabulary command through normal cog discovery."""
    await bot.add_cog(AdvancedSpanish(bot))
