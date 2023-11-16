from random import choice
from cogs.convo_starter_cog.convo_starter_help import categories, get_random_question
from discord.ext import commands
from base_cog import BaseCog, COLORS as colors
from discord import Embed

# Embed Message
ERROR_MESSAGE = "The proper format is `$topic <topic>` eg. `$topic 2`. Please see " \
                "`$help topic` for more info"
NOT_FOUND = "Topic not found! Please type ``$lst`` to see a list of topics"

# Spa and Eng Channel IDs
spa_channels = [809349064029241344, 243858509123289089, 388539967053496322, 477630693292113932]
#  personal server, spa-eng, spa-eng, esp-ing
# eng_channels = []


def embed_question(question_1a, question_1b):
    embed = Embed(color=choice(colors))
    embed.clear_fields()
    embed.title = question_1a
    embed.description = f"**{question_1b}**"
    return embed


class ConvoStarter(BaseCog):

    def __init__(self, bot):
        super().__init__(bot)

    @commands.command(aliases=['top', ])
    async def topic(self, ctx, *category):
        """
        Command used to suggestion a random conversation topic. Type `$topic <category>`.
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

        if ctx.channel.id in spa_channels:
            emb = embed_question(question_spa_eng[0], question_spa_eng[1])
        else:
            emb = embed_question(question_spa_eng[1], question_spa_eng[0])
        await ctx.send(embed=emb)


async def setup(bot):
    await bot.add_cog(ConvoStarter(bot))
