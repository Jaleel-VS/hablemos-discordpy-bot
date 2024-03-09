import os
from discord import Game
import discord
from discord.ext.commands import Bot, CommandNotFound, CommandOnCooldown
from logger import setup_logging
import logging
from bot_config import environment_selector

# Define a variable to select the environment
environment_name = 'dev'  # accepted values: 'development', 'dev', 'production', 'prod'

# Select the configuration based on the environment variable
ActiveConfig = environment_selector(environment_name)

if not ActiveConfig:
    logging.error(f"Invalid environment name {environment_name}")
    exit(1)

# Accessing configuration values
logging.info(f"Environment: {environment_name}")
bot_token = ActiveConfig.BOT_TOKEN
prefix = ActiveConfig.PREFIX
bot_url = ActiveConfig.BOT_URL


# Configure logging
setup_logging()

# Channel Codes

BOT_PLAYGROUND = 731403448502845501
ERROR_CHANNEL = 811669166883995690
ONLINE_CHANNEL = 808679873837137940



class Hablemos(Bot):

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
        for folder in os.listdir('./cogs'):
            if folder.endswith('_cog'):
                for file in os.listdir(f'./cogs/{folder}'):
                    if file.endswith('.py') and not file.startswith('_'):
                        try:
                            await self.load_extension(f'cogs.{folder}.{file[:-3]}')
                            logging.info(f'Loaded extension: {file[:-3]}')
                        except Exception as e:
                            logging.error(f'Failed to load extension {file[:-3]}.', exc_info=e)
                    
            

    async def on_ready(self):
        guild_id = BOT_PLAYGROUND
        guild = self.get_guild(guild_id)

        if guild is None:
            logging.warning(f"Guild with ID {guild_id} not found")
            return

        self.error_channel = guild.get_channel(ERROR_CHANNEL)
        self.online_channel = guild.get_channel(ONLINE_CHANNEL)

        logging.info("BOT LOADED!")

        if isinstance(self.online_channel, discord.TextChannel):
            await self.online_channel.send("I'm online bra :smiling_imp:")

        await self.change_presence(activity=Game(f'{self.command_prefix}help'))

    async def on_command_error(self, ctx, error):
        if ctx.message.content[1].isdigit() or ctx.message.content[-1] == self.command_prefix:
            return

        if isinstance(error, CommandNotFound):
            if isinstance(self.error_channel, discord.TextChannel):
                await self.error_channel.send(
                    f"------\nCommand not found:\n{ctx.author}, {ctx.author.id}, {ctx.channel}, {ctx.channel.id}, "
                    f"{ctx.guild}, {ctx.guild.id}, \n{ctx.message.content}\n{ctx.message.jump_url}\n------")
            logging.warning(f"Command not found: {ctx.message.content}")

        elif isinstance(error, CommandOnCooldown):
            if isinstance(ctx.channel, discord.TextChannel):
                await ctx.send(f"This command is on cooldown. Try again in {round(error.retry_after)} seconds.")
            logging.info(f"Command on cooldown: {ctx.message.content}")

        else:
            logging.error(f'Unhandled error: {error} in command {ctx.command}')
            if isinstance(ctx.channel, discord.TextChannel):
                await ctx.send("An unexpected error occurred. Please try again later.")

    async def on_command_completion(self, ctx):
        logging.info(f'Command {ctx.command} completed successfully by {ctx.author} in {ctx.guild}.')

# Initialize bot

bot = Hablemos(prefix)

# Run the bot
if bot_token is None:
    logging.error("No token found")
else:
    bot.run(bot_token)
