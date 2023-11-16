from discord.ext import commands
from cogs.hangman_cog.hangman import Hangman
from cogs.hangman_cog.hangman_help import get_word
from base_cog import BaseCog

categories = ['animales', 'profesiones', 'ciudades']


class HangmanController(BaseCog):
    def __init__(self, bot):
        super().__init__(bot)
        self.game_in_progress = False
        self.channels = []

    @commands.command(aliases=['hm', 'hang', ])
    async def hangman(self, ctx, *category):
        """
        (still experimental, please let me know of any errors)
        Categories:
        `animales` (199)
        `profesiones` (141)
        `ciudades` (49) (son las ciudades hispanohablantes más grandes)

        Type `$hangman <category>` to start a new game, eg `hangman profesiones`, `hangman animales`
        No input defaults to `animales`
        Type `quit` to exit the game, only the person who started can quit the game.
        The game will automatically exit after 45 seconds if there's no input
        """
        cat = ''
        if len(category) >= 1 and category[0] not in categories:
            return await ctx.send("""
            Category not found, available categories: `animales`, `profesiones`, `ciudades`. 
            See $help hangman for more info
            """)

        cat = 'animales' if len(category) == 0 else category[0]
        words = get_word(cat)

        channel = ctx.channel.id
        await self.new_game(ctx, channel, cat, words)

    async def new_game(self, context, channel, cat, words):
        if self.game_in_progress and channel in self.channels:
            return await context.send("There's already a game in progress in this channel")
        self.channels.append(channel)
        self.game_in_progress = True
        new_game = Hangman(self.bot, words, cat)
        await new_game.game_loop(context)
        self.channels.remove(channel)


async def setup(bot):
    await bot.add_cog(HangmanController(bot))
