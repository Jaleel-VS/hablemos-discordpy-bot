"""Unlisted advanced English vocabulary command with Spanish translations."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from discord.ext import commands

from cogs.utils.vocabulary import VocabularyCog

if TYPE_CHECKING:
    from hablemos import Hablemos

DATA_DIR = Path(__file__).resolve().parent / "data"


class AdvancedEnglish(VocabularyCog):
    """An unlisted collection of precise English vocabulary and usage examples."""

    def __init__(self, bot: Hablemos) -> None:
        super().__init__(bot, DATA_DIR, "en")

    @commands.command(name="e", hidden=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def vocabulary(self, ctx: commands.Context, *, query: str = "") -> None:
        """Browse advanced English; optionally find a term, e.g. $e acerbic."""
        await self.show_card(ctx, query)


async def setup(bot: Hablemos) -> None:
    """Load the hidden English vocabulary command through normal cog discovery."""
    await bot.add_cog(AdvancedEnglish(bot))
