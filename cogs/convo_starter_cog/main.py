"""Conversation starter cog — random bilingual discussion topics."""
from random import choice

from discord import Embed
from discord.ext import commands

from base_cog import COLORS as colors
from base_cog import BaseCog
from cogs.convo_starter_cog.convo_starter_help import (
    categories,
    get_random_question,
)
from cogs.utils.embeds import green_embed

SOURCE_URL = 'https://docs.google.com/spreadsheets/d/10jsNQsSG9mbLZgDoYIdVrbogVSN7eAKbOfCASA5hN0A/edit?usp=sharing'

# Embed Message
ERROR_MESSAGE = "The proper format is `$topic <topic>` eg. `$topic 2`. Please see " \
                "`$help topic` for more info"
NOT_FOUND = "Topic not found! Please type ``$lst`` to see a list of topics"

def embed_question(question_1a, question_1b):
    embed = Embed(color=choice(colors))
    embed.clear_fields()
    embed.title = question_1a
    embed.description = f"**{question_1b}**"
    return embed

class ConvoStarter(BaseCog):
    """Random conversation starters and discussion topics."""

    def __init__(self, bot):
        super().__init__(bot)
        self.spa_channels = set(bot.settings.convo_spa_channels)

    @commands.command(aliases=['top', ])
    async def topic(self, ctx, *category):
        """
        Suggest a random conversation topic.

        Just typing `$topic` will suggest a topic from the `general` category.
        Type `$lst` to see the list of categories.

        Examples: `$topic`, `$topic phil`, `$topic 4`"""
        table = ""
        if len(category) > 1:
            return await ctx.send(ERROR_MESSAGE)
        if len(category) == 0:
            table = "general"
        elif category[0] in categories:
            table = category[0]
        elif category[0] in ['1', '2', '3', '4']:
            table = categories[int(category[0]) - 1]
        else:
            return await ctx.send(NOT_FOUND)

        question_spa_eng = get_random_question(table)

        if ctx.channel.id in self.spa_channels:
            emb = embed_question(question_spa_eng[0], question_spa_eng[1])
        else:
            emb = embed_question(question_spa_eng[1], question_spa_eng[0])
        await ctx.send(embed=emb)

    @commands.command(aliases=['list'])
    async def lst(self, ctx):
        """Lists available topic categories."""
        text = (
            "To use any one of the undermentioned topics type `$topic <category>`.\n"
            "`$topic` or `$top` defaults to `general`\n\n"
            "command(category) - description:\n"
            "`general`, `1` - General questions\n"
            "`phil`, `2` - Philosophical questions\n"
            "`would`, `3` - *'Would you rather'* questions\n"
            "`other`, `4` -  Random questions\n\n"
            f"[Full list of questions]({SOURCE_URL})"
        )
        await ctx.send(embed=green_embed(text))


async def setup(bot):
    await bot.add_cog(ConvoStarter(bot))
