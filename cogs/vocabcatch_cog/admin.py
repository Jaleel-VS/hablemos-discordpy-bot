"""Owner-only admin group for Vocab Catch (`$vocatchadmin`).

Seed the card pool, force a spawn for testing, add a card, preview art,
and view pool/channel stats.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

import discord
from discord.ext import commands

from base_cog import BaseCog
from cogs.utils.embeds import blue_embed, green_embed, red_embed

from . import renderer
from .catch_logic import resolve_card
from .config import (
    MODE_SHOW_ES,
    RARITY_LABELS,
    channel_modes,
)
from .renderer import Card
from .seed import SEED_CARDS

if TYPE_CHECKING:

    from .main import VocabCatch

logger = logging.getLogger(__name__)


class VocabCatchAdmin(BaseCog):
    """Owner-only `$vocatchadmin` group."""

    @commands.group(name="vocatchadmin", invoke_without_command=True)
    @commands.is_owner()
    async def vocatchadmin(self, ctx: commands.Context) -> None:
        """Admin tools for the Vocab Catch minigame."""
        await ctx.send("Usage: `$vocatchadmin <seed|spawn|addcard|preview|stats>`")

    @vocatchadmin.command(name="seed")
    @commands.is_owner()
    async def seed(self, ctx: commands.Context) -> None:
        """Seed the starter card pool (only when the pool is empty)."""
        existing = await self.bot.db.count_pool_cards()
        if existing:
            await ctx.send(embed=blue_embed(
                f"Pool already has {existing} active card(s); seed skipped."))
            return
        for word_es, word_en, pos, gender, ex_es, ex_en, rarity in SEED_CARDS:
            await self.bot.db.add_card(
                word_es, word_en, part_of_speech=pos, gender=gender,
                example_es=ex_es, example_en=ex_en, rarity=rarity)
        await ctx.send(embed=green_embed(f"Seeded {len(SEED_CARDS)} cards into the pool."))
        logger.info("vocatch: pool seeded with %s cards by %s", len(SEED_CARDS), ctx.author)

    @vocatchadmin.command(name="spawn")
    @commands.is_owner()
    async def spawn(self, ctx: commands.Context) -> None:
        """Force an immediate spawn in the current channel (must be a game channel)."""
        cog = self.bot.get_cog("VocabCatch")
        if cog is None:
            await ctx.send(embed=red_embed("VocabCatch cog not loaded."))
            return
        # Cross-cog access via get_cog is dynamic; narrow to the concrete cog.
        cog = cast("VocabCatch", cog)
        if not isinstance(ctx.channel, (discord.TextChannel, discord.Thread, discord.VoiceChannel)):
            await ctx.send(embed=red_embed("This channel isn't a Vocab Catch channel."))
            return
        state = cog._channels.get(ctx.channel.id)
        if state is None:
            configured = ", ".join(f"<#{c}>" for c in channel_modes()) or "none configured"
            await ctx.send(embed=red_embed(
                f"This channel isn't a Vocab Catch channel. Configured: {configured}."))
            return
        if state.active is not None:
            await ctx.send(embed=red_embed("A wild card is already active here."))
            return
        await cog._spawn(ctx.channel, state)

    @vocatchadmin.command(name="addcard")
    @commands.is_owner()
    async def addcard(
        self, ctx: commands.Context, rarity: int, word_es: str, *, word_en: str,
    ) -> None:
        """Add a card: `$vocatchadmin addcard <1-5> "<word_es>" <word_en>`."""
        if not 1 <= rarity <= 5:
            await ctx.send(embed=red_embed("Rarity must be 1–5."))
            return
        card_id = await self.bot.db.add_card(word_es, word_en, rarity=rarity)
        await ctx.send(embed=green_embed(
            f"Added card #{card_id:04d} — **{word_es}** / {word_en} "
            f"({RARITY_LABELS[rarity]})."))

    @vocatchadmin.command(name="preview")
    @commands.is_owner()
    async def preview(self, ctx: commands.Context, card_id: int, mode: str = MODE_SHOW_ES) -> None:
        """Render a card (revealed) in a given mode to preview the art.

        mode: `show_es` (default), `en_to_es`, or `es_to_en`.
        """
        card = await self.bot.db.get_card(card_id)
        if card is None:
            await ctx.send(embed=red_embed(f"No card #{card_id}."))
            return
        view = resolve_card(card, mode)
        # get_card returns a plain row dict carrying the Card fields; the
        # renderer's view: dict param also can't take a CardView TypedDict
        # directly, so cast both (identical at runtime).
        buf = renderer.render_card(cast(Card, card), cast(dict, view), revealed=True)
        await ctx.send(file=discord.File(buf, filename="preview.png"))

    @vocatchadmin.command(name="stats")
    @commands.is_owner()
    async def stats(self, ctx: commands.Context) -> None:
        """Show pool size and configured channels/modes."""
        n = await self.bot.db.count_pool_cards()
        modes = channel_modes()
        if modes:
            chans = "\n".join(f"• <#{cid}> — `{mode}`" for cid, mode in modes.items())
        else:
            chans = "none configured (set VOCATCH_*_CHANNEL_ID)"
        await ctx.send(embed=blue_embed(
            f"**Active cards:** {n}\n**Channels:**\n{chans}"))
