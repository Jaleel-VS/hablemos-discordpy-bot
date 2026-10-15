"""Advanced English vocabulary slash command with Spanish translations."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from discord import Interaction, app_commands

from cogs.utils.vocabulary import VocabularyCog

if TYPE_CHECKING:
    from hablemos import Hablemos

DATA_DIR = Path(__file__).resolve().parent / "data"


class AdvancedEnglish(VocabularyCog):
    """A collection of precise English vocabulary and usage examples."""

    def __init__(self, bot: Hablemos) -> None:
        super().__init__(bot, DATA_DIR, "en")

    @app_commands.command(name="e", description="Browse advanced English vocabulary or find a term")
    @app_commands.describe(query="Optional word or headword fragment to find, e.g. acerbic")
    @app_commands.checks.cooldown(1, 5)
    async def vocabulary(self, interaction: Interaction, query: str = "") -> None:
        """Browse advanced English; optionally find a term."""
        await self.show_card(interaction, query)


async def setup(bot: Hablemos) -> None:
    """Load the English vocabulary slash command through normal cog discovery."""
    await bot.add_cog(AdvancedEnglish(bot))
