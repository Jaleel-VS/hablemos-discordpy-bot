"""Advanced Spanish vocabulary slash command."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from discord import Interaction, app_commands

from cogs.utils.vocabulary import VocabularyCog

if TYPE_CHECKING:
    from hablemos import Hablemos

DATA_DIR = Path(__file__).resolve().parent / "data"


class AdvancedSpanish(VocabularyCog):
    """A collection of precise Spanish vocabulary and usage examples."""

    def __init__(self, bot: Hablemos) -> None:
        super().__init__(bot, DATA_DIR, "es")

    @app_commands.command(name="c", description="Browse advanced Spanish vocabulary or find a term")
    @app_commands.describe(query="Optional word or headword fragment to find, e.g. explayarse")
    @app_commands.checks.cooldown(1, 5)
    async def vocabulary(self, interaction: Interaction, query: str = "") -> None:
        """Browse advanced Spanish; optionally find a term."""
        await self.show_card(interaction, query)


async def setup(bot: Hablemos) -> None:
    """Load the Spanish vocabulary slash command through normal cog discovery."""
    await bot.add_cog(AdvancedSpanish(bot))
