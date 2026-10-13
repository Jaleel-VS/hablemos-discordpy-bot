"""Did You Know? cog — bilingual Spanish/English fun facts with per-channel no-repeat cycles."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import AllowedMentions, ui
from discord.ext import commands

from base_cog import BaseCog

if TYPE_CHECKING:
    from db.facts import FunFact
    from hablemos import Hablemos

logger = logging.getLogger(__name__)

_ACCENT = discord.Color.from_str("#1abc9c")


def build_fact_view(fact: FunFact) -> ui.LayoutView:
    """Build a sourced Spanish/English Components V2 fact card."""
    source_line = f"-# Fuente / Source: [{fact.source_name}](<{fact.source_url}>)"

    view = ui.LayoutView(timeout=None)
    view.add_item(
        ui.Container(
            ui.TextDisplay("## ¿Sabías que? / Did you know?"),
            ui.Separator(visible=True),
            ui.TextDisplay(f"**Español**\n{fact.es}"),
            ui.TextDisplay(f"**English**\n{fact.en}"),
            ui.Separator(visible=True),
            ui.TextDisplay(source_line),
            accent_colour=_ACCENT,
        )
    )
    return view


class DyiCog(BaseCog):
    """Bilingual Did You Know? facts with per-channel persistent no-repeat cycles."""

    def __init__(self, bot: Hablemos) -> None:
        super().__init__(bot)

    async def cog_load(self) -> None:
        """Seed the fact catalog into the database on cog startup."""
        await self.bot.db.seed_facts()
        logger.info("DyiCog loaded — fact catalog seeded")

    @commands.command(name="dyi", help="Get a bilingual Did You Know? fact.")
    @commands.cooldown(rate=1, per=5, type=commands.BucketType.user)
    async def dyi(self, ctx: commands.Context) -> None:
        """Get a bilingual fun fact; all facts cycle once per channel before repeating."""
        try:
            fact: FunFact = await self.bot.db.next_fact(ctx.channel.id)
            await ctx.send(view=build_fact_view(fact), allowed_mentions=AllowedMentions.none())
        except LookupError:
            await ctx.send(
                "Aún no hay datos disponibles. / No facts are available yet.",
                allowed_mentions=AllowedMentions.none(),
            )
            return
        except discord.HTTPException:
            logger.exception("Failed to deliver a bilingual fact card")
            await ctx.send(
                "Could not send the fact card right now. Try again in a moment.\n"
                "No se pudo enviar la tarjeta ahora. Inténtalo de nuevo.",
                allowed_mentions=AllowedMentions.none(),
            )
            return


async def setup(bot: Hablemos) -> None:
    """Register the DyiCog with the bot (called by discord.py extension loader)."""
    await bot.add_cog(DyiCog(bot))
    logger.info("DyiCog registered")
