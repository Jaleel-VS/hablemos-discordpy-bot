"""Conversation starter cog — random bilingual discussion topics."""

from __future__ import annotations

from random import choice
from typing import TYPE_CHECKING

from discord import Embed
from discord.ext import commands

from base_cog import COLORS, BaseCog
from cogs.convo_starter_cog.questions import (
    CATEGORY_DESCRIPTIONS,
    QuestionBank,
    load_questions,
    resolve_category,
)
from cogs.utils.embeds import green_embed

if TYPE_CHECKING:
    from hablemos import Hablemos

SOURCE_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "10jsNQsSG9mbLZgDoYIdVrbogVSN7eAKbOfCASA5hN0A/edit?usp=sharing"
)


def question_embed(primary: str, translation: str) -> Embed:
    """Build a bilingual conversation-starter embed."""
    return Embed(
        description=f"**{primary}**\n\n{translation}",
        color=choice(COLORS),
    )


def embed_question(primary: str, translation: str) -> Embed:
    """Backward-compatible alias for :func:`question_embed`."""
    return question_embed(primary, translation)


class ConvoStarter(BaseCog):
    """Random conversation starters and discussion topics."""

    def __init__(self, bot: Hablemos) -> None:
        super().__init__(bot)
        self.spanish_first_channels = frozenset(
            bot.settings.convo_spa_channels
        )
        self.questions: QuestionBank = load_questions()

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

        spanish, english = choice(self.questions[resolved_category])
        if ctx.channel.id in self.spanish_first_channels:
            primary, translation = spanish, english
        else:
            primary, translation = english, spanish
        await ctx.send(embed=question_embed(primary, translation))

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
