import os
from discord import Game, Intents
import discord
from discord.ext.commands import Bot, CommandNotFound, CommandOnCooldown
from dotenv import load_dotenv

load_dotenv('.env')




class Hablemos(Bot):
    error_channel = ""
    online_channel = ""

    def __init__(self, prefix):
        super().__init__(description="Bot by Jaleel#6408",
                         command_prefix=prefix,
                         owner_id=216848576549093376,
                         help_command=None,
                         intents=discord.Intents.all()
                         )

        self.online_channel = None
        self.error_channel = None

        
    
    async def setup_hook(self):
        for filename in os.listdir("./cogs"):
            if filename.endswith(".py"):
                try:
                    await self.load_extension(f"cogs.{filename[:-3]}")
                    print(f"Loaded {filename}")
                except Exception as e:
                    print(f"Failed to load {filename}")
                    print(f"[ERROR] {e}")


    async def on_ready(self):
        # error log in my personal server
        guild_id = 731403448502845501
        guild = self.get_guild(guild_id)

        if guild is None:
            print(f"Guild with ID {guild_id} not found")
            return
        self.error_channel = guild.get_channel(811669166883995690)
        self.online_channel = guild.get_channel(808679873837137940)
        print("BOT LOADED!")

        if isinstance(self.online_channel, discord.TextChannel):
            await self.online_channel.send("I'm online bra :smiling_imp:")
            
        await self.change_presence(activity=Game(f'{PREFIX}help'))

    async def on_command_error(self, ctx, error):
        if ctx.message.content[1].isdigit() or ctx.message.content[-1] == PREFIX:  # ignores dollar amounts and math bot
            return
        if isinstance(error, CommandNotFound):
            if isinstance(self.error_channel, discord.TextChannel):
                await self.error_channel.send(
                    f"------\nCommand not found:\n{ctx.author}, {ctx.author.id}, {ctx.channel}, {ctx.channel.id}, "
                    f"{ctx.guild}, {ctx.guild.id}, \n{ctx.message.content}\n{ctx.message.jump_url}\n------")

        if isinstance(error, CommandOnCooldown):
            if isinstance(ctx.channel, discord.TextChannel):
                await ctx.send(f"This command is on cooldown.  Try again in {round(error.retry_after)} seconds.")

    async def on_command_completion(self, ctx):
        if isinstance(self.error_channel, discord.TextChannel):
            await self.error_channel.send(
                f"------\nSuccessfully used by {ctx.author}, {ctx.channel},{ctx.guild}, "
                f"{ctx.message.content}\n{ctx.message.jump_url}\n------")


PREFIX = os.getenv('PREFIX')
bot = Hablemos(PREFIX)

bot_token = os.getenv('BOT_TOKEN')

if bot_token is None:
    print("No token found")
else:
    bot.run(bot_token)
