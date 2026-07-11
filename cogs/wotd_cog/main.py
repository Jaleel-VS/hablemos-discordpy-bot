"""Word of the Day cog — daily vocab cards with Pillow rendering + MediaGallery."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from discord import File, ui
from discord.components import MediaGalleryItem
from discord.ext import commands

from base_cog import BaseCog
from cogs.wotd_cog.renderer import render_wotd_card

if TYPE_CHECKING:
    from hablemos import Hablemos

logger = logging.getLogger(__name__)

# Static word bank — later this could pull from the DB or an API
WORDS = {
    "beginner_en": {
        "word": "however",
        "translation": "sin embargo",
        "example": "I wanted to go; however, it started raining.",
    },
    "beginner_es": {
        "word": "mientras",
        "translation": "while / meanwhile",
        "example": "Ella cocinaba mientras él leía un libro.",
    },
    "advanced_en": {
        "word": "ubiquitous",
        "translation": "omnipresente / ubicuo",
        "example": "Smartphones have become ubiquitous in modern society.",
    },
    "advanced_es": {
        "word": "desvelarse",
        "translation": "to stay up all night / to lose sleep over",
        "example": "Me desvelé estudiando para el examen de mañana.",
    },
}


class WotdView(ui.LayoutView):
    """Components V2 layout for the WOTD post with a MediaGallery."""

    def __init__(self, files: list[File]):
        super().__init__()
        # Header
        self.add_item(ui.TextDisplay("# 📖 Word of the Day"))
        self.add_item(ui.Separator())

        # Gallery with all 4 cards
        descriptions = [
            "» Beginner English", "» Beginner Spanish",
            "★ Advanced English", "★ Advanced Spanish",
        ]
        items = [
            MediaGalleryItem(f"attachment://{f.filename}", description=desc)
            for f, desc in zip(files, descriptions, strict=True)
        ]
        gallery = ui.MediaGallery(*items)
        self.add_item(gallery)

        # Footer text
        self.add_item(ui.Separator())
        self.add_item(ui.TextDisplay(
            "-# Try using today's words in a sentence! Practice makes perfect 💪"
        ))


class WotdCog(BaseCog):
    """Word of the Day — shows 4 vocab cards in a media gallery."""

    @commands.command(name="wotd")
    @commands.cooldown(1, 30, commands.BucketType.channel)
    async def wotd(self, ctx: commands.Context):
        """Post the Word of the Day cards."""
        if not ctx.guild:
            await ctx.send("This command can only be used in a server.")
            return

        async with ctx.typing():
            files, view = _build_wotd()

        await ctx.send(view=view, files=files)


def _build_wotd() -> tuple[list[File], WotdView]:
    """Render all 4 cards and construct the LayoutView."""
    card_types = ["beginner_en", "beginner_es", "advanced_en", "advanced_es"]
    files: list[File] = []

    for card_type in card_types:
        data = WORDS[card_type]
        buf = render_wotd_card(
            card_type,
            word=data["word"],
            translation=data["translation"],
            example=data["example"],
        )
        files.append(File(buf, filename=f"wotd_{card_type}.png"))

    view = WotdView(files)
    return files, view


async def setup(bot: Hablemos):
    await bot.add_cog(WotdCog(bot))
