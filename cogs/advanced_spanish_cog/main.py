"""Unlisted advanced Spanish vocabulary browser with bilingual study cards."""

from __future__ import annotations

import asyncio
import logging
import random
from typing import TYPE_CHECKING

import discord
from discord import ui
from discord.ext import commands

from base_cog import BaseCog
from cogs.advanced_spanish_cog.catalog import (
    VocabularyEntry,
    find_entries,
    load_catalog,
)

if TYPE_CHECKING:
    from hablemos import Hablemos

logger = logging.getLogger(__name__)

_REFERENCE_URL = (
    "https://cvc.cervantes.es/ensenanza/biblioteca_ele/plan_curricular/"
    "niveles/08_nociones_generales_inventario_c1-c2.htm"
)
_ACCENTS = {
    "neutro": discord.Color.teal(),
    "coloquial": discord.Color.gold(),
    "formal": discord.Color.blurple(),
    "literario": discord.Color.purple(),
}


class VocabularyView(ui.LayoutView):
    """Browse a fixed deck; only its invoker can navigate or toggle English."""

    def __init__(self, entries: tuple[VocabularyEntry, ...], invoker_id: int) -> None:
        if not entries:
            raise ValueError("A vocabulary browser needs at least one entry")
        super().__init__(timeout=600)
        self.entries = entries
        self.invoker_id = invoker_id
        self.index = 0
        self.show_english = True
        self.expired = False
        self.message: discord.Message | None = None
        self._lock = asyncio.Lock()
        self._rebuild()

    def _rebuild(self) -> None:
        entry = self.entries[self.index]
        escape = discord.utils.escape_markdown
        region = "Uso general" if entry.region == "general" else entry.region
        meaning = f"### Qué significa\n{escape(entry.meaning_es)}"
        if self.show_english:
            meaning += f"\n*{escape(entry.meaning_en)}*"
        examples = ["### En contexto"]
        for number, example in enumerate(entry.examples, start=1):
            examples.append(f"**{number:02d}** {escape(example.es)}")
            if self.show_english:
                examples.append(f"-# {escape(example.en)}")
        previous = ui.Button(
            label="Anterior", style=discord.ButtonStyle.secondary,
            disabled=self.expired or self.index == 0,
        )
        previous.callback = self._previous
        next_button = ui.Button(
            label="Siguiente", style=discord.ButtonStyle.primary,
            disabled=self.expired or self.index == len(self.entries) - 1,
        )
        next_button.callback = self._next
        english = ui.Button(
            label="Ocultar inglés" if self.show_english else "Mostrar inglés",
            disabled=self.expired,
        )
        english.callback = self._toggle_english
        status = "Sesión finalizada" if self.expired else "10 min de inactividad"
        self.clear_items()
        self.add_item(ui.Container(
            ui.TextDisplay(
                f"-# LÉXICO · ESPAÑOL AVANZADO\n## {escape(entry.term)}\n"
                f"-# {entry.register.capitalize()} · {escape(region)}"
            ),
            ui.TextDisplay(meaning),
            ui.Separator(),
            ui.TextDisplay("\n\n".join(examples)),
            ui.Separator(),
            ui.TextDisplay(
                f"**Combinación natural**\n{escape(entry.collocation)}\n\n"
                f"**Matiz de uso**\n{escape(entry.note)}"
            ),
            ui.TextDisplay(
                f"-# {self.index + 1} / {len(self.entries)} · Ejemplos originales · {status}"
            ),
            ui.ActionRow(
                previous, next_button, english,
                ui.Button(label="Inventario Cervantes", style=discord.ButtonStyle.link, url=_REFERENCE_URL),
            ),
            accent_colour=_ACCENTS[entry.register],
        ))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Keep other readers from changing the invoker's study card."""
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message(
                "Esta tarjeta tiene otro lector. Usa `$c` para abrir la tuya.",
                ephemeral=True, allowed_mentions=discord.AllowedMentions.none(),
            )
            return False
        return True

    async def _change(self, interaction: discord.Interaction, *, step: int = 0, toggle: bool = False) -> None:
        await interaction.response.defer()
        async with self._lock:
            if self.expired:
                return
            previous_index, previous_english = self.index, self.show_english
            self.index = max(0, min(len(self.entries) - 1, self.index + step))
            if toggle:
                self.show_english = not self.show_english
            self._rebuild()
            try:
                await interaction.edit_original_response(view=self, allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:
                self.index, self.show_english = previous_index, previous_english
                self._rebuild()
                raise

    async def _previous(self, interaction: discord.Interaction) -> None:
        await self._change(interaction, step=-1)

    async def _next(self, interaction: discord.Interaction) -> None:
        await self._change(interaction, step=1)

    async def _toggle_english(self, interaction: discord.Interaction) -> None:
        await self._change(interaction, toggle=True)

    async def on_timeout(self) -> None:
        """Leave the last card readable and disable its expired study controls."""
        async with self._lock:
            self.expired = True
            self._rebuild()
            if self.message is None:
                return
            try:
                await self.message.edit(view=self, allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:
                logger.exception("Unable to expire an advanced vocabulary card")

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: ui.Item) -> None:
        """Log interaction failures without exposing exception details to readers."""
        logger.error("Advanced vocabulary interaction failed", exc_info=(type(error), error, error.__traceback__))
        try:
            text = "No se pudo actualizar la tarjeta. Vuelve a intentarlo. / Could not update the card. Please try again."
            if interaction.response.is_done():
                await interaction.followup.send(text, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
            else:
                await interaction.response.send_message(text, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            logger.exception("Unable to send the vocabulary interaction error response")


class AdvancedSpanish(BaseCog):
    """An unlisted collection of precise vocabulary, idioms, and usage examples."""

    def __init__(self, bot: Hablemos) -> None:
        super().__init__(bot)
        self.entries = load_catalog()

    @commands.command(name="c", hidden=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def vocabulary(self, ctx: commands.Context, *, query: str = "") -> None:
        """Browse advanced Spanish; optionally find a term, e.g. $c explayarse."""
        matches = find_entries(self.entries, query)
        try:
            if not matches:
                self.vocabulary.reset_cooldown(ctx)
                await ctx.send(
                    "No encontré ese término. Prueba otra palabra o usa `$c` sin argumentos.",
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                return
            if not query.strip():
                deck = list(matches)
                random.shuffle(deck)
                matches = tuple(deck)
            view = VocabularyView(matches, ctx.author.id)
            view.message = await ctx.send(view=view, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            logger.exception("Unable to send an advanced vocabulary card")


async def setup(bot: Hablemos) -> None:
    """Load the hidden vocabulary command through normal cog discovery."""
    await bot.add_cog(AdvancedSpanish(bot))
