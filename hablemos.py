import sys
import traceback
from os import getenv, path

import discord
from discord import Game, Intents
from discord.ext.commands import Bot, CommandNotFound, CommandOnCooldown
from dotenv import load_dotenv

load_dotenv('.env')

PREFIX = "$"  # the real one, have to make it configurable some day
# PREFIX = "-"  # for testing


cog_extensions = ['cogs.convo_starter_cog',
                  'cogs.general_cog',
                  'cogs.hangman_cog',
                  'cogs.quote_generator_cog',
                  'cogs.reverso_cog']


class Hablemos(Bot):
    error_channel = ""
    online_channel = ""

    def __init__(self):
        super().__init__(description="Bot by Jaleel#6408",
                         command_prefix=PREFIX,
                         owner_id=216848576549093376,
                         help_command=None,
                         intents=Intents(members=True, messages=True, guilds=True, message_content=True)
                         )

    async def setup_hook(self) -> None:
        # load cogs
        for extension in cog_extensions:
            try:
                await self.load_extension(f'{extension}.main')
                print(f"{extension} loaded")
            except Exception:
                print(f'Failed to load {extension}', file=sys.stderr)
                traceback.print_exc()
                raise

    async def on_ready(self):
        # error log in my personal server
        try:
            self.error_channel = self.get_guild(731403448502845501).get_channel(811669166883995690)
            self.online_channel = self.get_guild(731403448502845501).get_channel(808679873837137940)
        except AttributeError:
            self.error_channel = None
            self.online_channel = None
        print("BOT LOADED!")
        if self.online_channel:
            await self.online_channel.send("I'm online bra :smiling_imp:")
        await self.change_presence(activity=Game(f'{PREFIX}help'))

    async def on_command_error(self, ctx, error):
        if ctx.message.content[1].isdigit() or ctx.message.content[-1] == PREFIX:  # ignores dollar amounts and math bot
            return
        if isinstance(error, CommandNotFound):
            if self.error_channel:
                await self.error_channel.send(
                    f"------\nCommand not found:\n{ctx.author}, {ctx.author.id}, {ctx.channel}, {ctx.channel.id}, "
                    f"{ctx.guild}, {ctx.guild.id}, \n{ctx.message.content}\n{ctx.message.jump_url}\n------")
            else:
                raise error

        if isinstance(error, CommandOnCooldown):
            await ctx.send(f"This command is on cooldown.  Try again in {round(error.retry_after)} seconds.")

    async def on_command_completion(self, ctx):
        if self.error_channel:
            await self.error_channel.send(
                f"------\nSuccessfully used by {ctx.author}, {ctx.channel},{ctx.guild}, "
                f"{ctx.message.content}\n{ctx.message.jump_url}\n------")


# check if .env file exists, and if not, create it for the user
dir_path = path.dirname(path.realpath(__file__))
try:
    with open(f"{dir_path}/.env", 'r') as f:
        pass
except FileNotFoundError:
    txt = """BOT_TOKEN=\n"""
    with open(f'{dir_path}/.env', 'w') as f:
        f.write(txt)
    print("I've created a .env file for you, go in there and put your bot token in the file.")
    raise discord.LoginFailure

# check if the .env file exists but the BOT_TOKEN field is empty
token = getenv('BOT_TOKEN')
if not token:
    print("You need to put your bot token in the .env file in your bot directory.")
    raise discord.LoginFailure

# make it so the below code only executes if you RUN this file. It is ignored if you IMPORT this file
if __name__ == '__main__':
    bot = Hablemos()
    bot.run(token)
