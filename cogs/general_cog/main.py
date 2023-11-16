from discord.ext.commands import command
from base_cog import BaseCog
from discord import Embed, Color, Forbidden

SOURCE_URL = 'https://docs.google.com/spreadsheets/d/10jsNQsSG9mbLZgDoYIdVrbogVSN7eAKbOfCASA5hN0A/edit?usp=sharing'
REPO = 'https://github.com/Jaleel-VS/hablemos-discordpy-bot'
DPY = 'https://discordpy.readthedocs.io/en/latest/'
PYC = 'https://github.com/Pycord-Development/pycord'
INVITE_LINK = "https://discord.com/api/oauth2/authorize?client_id=808377026330492941&permissions=3072&scope=bot"

from hablemos import PREFIX as PREFIX_


def green_embed(text):
    return Embed(description=text, color=Color(int('00ff00', 16)))


class General(BaseCog):
    def __init__(self, bot):
        super().__init__(bot)

    @command()
    async def help(self, ctx, arg=''):
        if arg:
            requested = self.bot.get_command(arg)
            if not requested:
                await ctx.send("I was unable to find the command you requested")
                return
            message = ""
            message += f"**{PREFIX_}{requested.qualified_name}**\n"
            if requested.aliases:
                message += f"Aliases: `{'`, `'.join(requested.aliases)}`\n"
            if requested.help:
                message += requested.help
            emb = green_embed(message)
            await ctx.send(embed=emb)
        else:
            to_send = """
            Type `$help <command>` for more info about on any command.
            
            **General**: 
                `info` - Display information and a GitHub link to the source code
                `invite` - Invite the bot to your server
            **Conversation starters**: 
                `topic` - Displays random conversation starter 
                `lst` - Lists available categories
            **Hangman**
                `hangman` - Starts a new game with Spanish vocabulary
            **Quote generator** 
                `quote <message>` or `quote <message_link>` - Generates a "quote image" of a user's message
            **Reverso Contexto**
                `reverso <source_language> <target_language> <message>` - Find in-context examples in your target languages
            """
            await ctx.send(embed=green_embed(to_send))

    @command(aliases=['list', ])
    async def lst(self, ctx):
        """
        Lists available categories
        """
        categories = f"""    
        To use any one of the undermentioned topics type `$topic <category>`. 
        `$topic` or `$top` defaults to `general`
        
        command(category) - description:
        `general`, `1` - General questions
        `phil`, `2` - Philosophical questions
        `would`, `3` - *'Would you rather'* questions
        `other`, `4` -  Random questions

        [Full list of questions]({SOURCE_URL})        
        """
        await ctx.send(embed=green_embed(categories))

    @command()
    async def info(self, ctx):
        """
        Information about the bot
        """

        text = f"""
        The bot was coded in Python using the [Pycord]({PYC}) wrapper for  [discord.py]({DPY}) framework.
        
        To report an error or make a suggestion please message <@216848576549093376>
        [Github Repository]({REPO})
        """

        await ctx.send(embed=green_embed(text))

    @command()
    async def invite(self, ctx):
        """
        Bot invitation link
        """

        text = f"""
        [Invite the bot to your server]({INVITE_LINK})
        I still have to make the prefix configurable so for now you have to use `$`
        """

        await ctx.send(embed=green_embed(text))

    @command()
    async def ping(self, ctx):
        """
        Ping the bot to see if there are latency issues
        """
        await ctx.send(embed=green_embed(f"**Command processing time**: {round(self.bot.latency * 1000, 2)}ms"))

    @command()
    async def mystats(self, ctx):
        guilds = await self.bot.fetch_guilds().flatten()
        my_guilds = ''.join(f"{guild}\n" for guild in guilds)
        await ctx.send(f"The bot is in the following guilds: \n {my_guilds}")


async def setup(bot):
    await bot.add_cog(General(bot))
