"""Conversation starter cog — random bilingual discussion topics."""

from __future__ import annotations

from random import choice, sample
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from base_cog import BaseCog
from cogs.convo_starter_cog.questions import (
    CATEGORY_DESCRIPTIONS,
    QuestionBank,
    load_questions,
    resolve_category,
)
from cogs.convo_starter_cog.views import TopicCard
from cogs.utils.embeds import green_embed

if TYPE_CHECKING:
    from hablemos import Hablemos

SOURCE_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "10jsNQsSG9mbLZgDoYIdVrbogVSN7eAKbOfCASA5hN0A/edit?usp=sharing"
)

HINT_GAPS = (2, 3, 4)  # topics between category hints in a channel
HINT_CHOICES = 3       # other categories offered per hint


class ConvoStarter(BaseCog):
    """Random conversation starters and discussion topics."""

    def __init__(self, bot: Hablemos) -> None:
        super().__init__(bot)
        self.spanish_first_channels = frozenset(
            bot.settings.convo_spa_channels
        )
        self.questions: QuestionBank = load_questions()
        # Topics left until the next hint, per channel. Ephemeral pacing for a
        # UI nudge, not data: losing it on restart only shifts one hint.
        self._until_hint: dict[int, int] = {}
        # Hint buttons post public topics, so they share $topic's 5s/user rate.
        self._click_cooldown: commands.CooldownMapping[discord.Interaction] = (
            commands.CooldownMapping(
                commands.Cooldown(1, 5), lambda interaction: interaction.user.id
            )
        )

    def _hint_due(self, channel_id: int) -> bool:
        """Count one topic in *channel_id*; True on every 2nd–4th (random)."""
        left = self._until_hint.get(channel_id, choice(HINT_GAPS)) - 1
        if left > 0:
            self._until_hint[channel_id] = left
            return False
        self._until_hint[channel_id] = choice(HINT_GAPS)
        return True

    def _deal(self, channel_id: int, category: str) -> TopicCard:
        """Pick a question from *category* and build its card for *channel_id*."""
        spanish, english = choice(self.questions[category])
        if channel_id in self.spanish_first_channels:
            primary, translation = spanish, english
        else:
            primary, translation = english, spanish
        hints = (
            sample([c for c in CATEGORY_DESCRIPTIONS if c != category], HINT_CHOICES)
            if self._hint_due(channel_id)
            else []
        )
        return TopicCard(category, primary, translation, hints=hints, on_pick=self._pick)

    async def _pick(self, interaction: discord.Interaction, category: str) -> None:
        """Hint button: post a fresh topic from *category* in the same channel."""
        retry_after = self._click_cooldown.update_rate_limit(interaction)
        if retry_after:
            await interaction.response.send_message(
                f"Espera {retry_after:.0f}s. / Wait {retry_after:.0f}s.", ephemeral=True
            )
            return
        channel_id = interaction.channel_id
        if channel_id is None:  # buttons only exist on channel messages
            return
        card = self._deal(channel_id, category)
        await interaction.response.send_message(view=card)
        if card.buttons:
            card.message = await interaction.original_response()

    @commands.command(aliases=["top"])
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def topic(
        self,
        ctx: commands.Context,
        *,
        category: str = "general",
    ) -> None:
        """Suggest a random conversation topic.

        Categories can be selected by name or number. The default is
        ``general``. Examples: ``$topic``, ``$topic phil``, ``$topic 5``.
        """
        try:
            resolved_category = resolve_category(category)
        except ValueError:
            self.topic.reset_cooldown(ctx)
            await ctx.send(
                f"Topic not found. Type `{ctx.clean_prefix}lst` to see "
                "the available categories."
            )
            return

        card = self._deal(ctx.channel.id, resolved_category)
        message = await ctx.send(view=card)
        if card.buttons:
            card.message = message

    @commands.command(aliases=["list"])
    async def lst(self, ctx: commands.Context) -> None:
        """List available topic categories."""
        category_lines = "\n".join(
            f"`{category}`, `{index}` — {description}"
            for index, (category, description) in enumerate(
                CATEGORY_DESCRIPTIONS.items(), start=1
            )
        )
        text = (
            f"Use `{ctx.clean_prefix}topic <category>` to choose a category.\n"
            f"`{ctx.clean_prefix}topic` and `{ctx.clean_prefix}top` default "
            "to `general`.\n\n"
            f"{category_lines}\n\n"
            f"[Full list of questions]({SOURCE_URL})"
        )
        await ctx.send(embed=green_embed(text))


async def setup(bot: Hablemos) -> None:
    """Load the conversation starter cog."""
    await bot.add_cog(ConvoStarter(bot))
