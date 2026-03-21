import os
import logging
import random

import discord
from discord import Game
from discord.ext.commands import Bot, CommandNotFound, CommandOnCooldown, MissingPermissions, NotOwner

from logger import setup_logging
from db import Database

# Configure logging before anything else
setup_logging()
logger = logging.getLogger(__name__)

# Configuration from environment
bot_token = os.getenv('BOT_TOKEN')
if not bot_token:
    raise ValueError("BOT_TOKEN environment variable is required")

prefix = os.getenv('PREFIX', '$')

# Channel/guild IDs from environment with existing defaults for backwards compatibility
BOT_PLAYGROUND = int(os.getenv('BOT_PLAYGROUND_GUILD_ID', '731403448502845501'))
ERROR_CHANNEL = int(os.getenv('ERROR_CHANNEL_ID', '811669166883995690'))
ONLINE_CHANNEL = int(os.getenv('ONLINE_CHANNEL_ID', '808679873837137940'))
LEAGUE_GUILD_ID = int(os.getenv('LEAGUE_GUILD_ID', '243838819743432704'))
OWNER_ID = int(os.getenv('BOT_OWNER_ID', '216848576549093376'))

logger.info(f"Environment: {os.getenv('ENVIRONMENT', 'development')}")



class Hablemos(Bot):

    def __init__(self, prefix):
        super().__init__(description="Bot by Jaleel#6408",
                         command_prefix=prefix,
                         owner_id=OWNER_ID,
                         help_command=None,
                         intents=discord.Intents.all()
                         )

        self.online_channel = None
        self.error_channel = None
        self.db = Database()

    async def close(self):
        await self.db.close()
        await super().close()

    async def setup_hook(self):
        try:
            await self.db.connect()
            logger.info("Database connected successfully")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            return

        # Load disabled cogs set for filtering
        try:
            disabled = await self.db.get_disabled_cogs()
        except Exception:
            disabled = set()

        for folder in os.listdir('./cogs'):
            if folder.endswith('_cog'):
                cog_path = f'./cogs/{folder}'
                if os.path.isdir(cog_path):
                    for file in os.listdir(cog_path):
                        if file.endswith('.py') and file.startswith('main'):
                            ext = f'cogs.{folder}.{file[:-3]}'
                            if ext in disabled:
                                logger.info(f'Skipping disabled extension: {ext}')
                                continue
                            try:
                                await self.load_extension(ext)
                                logger.info(f'Loaded extension: {ext}')
                            except Exception as e:
                                logger.error(f'Failed to load extension {ext}: {e}', exc_info=True)

    async def on_ready(self):
        guild_id = BOT_PLAYGROUND
        guild = self.get_guild(guild_id)

        if guild is None:
            logger.warning(f"Guild with ID {guild_id} not found")
            return

        self.error_channel = guild.get_channel(ERROR_CHANNEL)
        self.online_channel = guild.get_channel(ONLINE_CHANNEL)

        logger.info("BOT LOADED!")

        # Sync slash commands
        try:
            # Global sync (can take up to 1 hour to propagate)
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} global slash command(s)")

            # Guild-specific sync for Language League (instant)
            league_guild = discord.Object(id=LEAGUE_GUILD_ID)
            synced_guild = await self.tree.sync(guild=league_guild)
            logger.info(f"Synced {len(synced_guild)} slash command(s) to Language League guild (instant)")
        except Exception as e:
            logger.error(f"Failed to sync slash commands: {e}")

        if isinstance(self.online_channel, discord.TextChannel):
            await self.online_channel.send("I'm online bra :smiling_imp:")

        await self.change_presence(activity=Game(f'{self.command_prefix}help'))

    async def on_command_error(self, ctx, error):
        if len(ctx.message.content) > 1 and (ctx.message.content[1].isdigit() or ctx.message.content[-1] == self.command_prefix):
            return

        # Record failed command metric
        try:
            cog_name = type(ctx.cog).__name__ if ctx.cog else None
            await self.db.record_command(
                command_name=str(ctx.command),
                cog_name=cog_name,
                user_id=ctx.author.id,
                guild_id=ctx.guild.id if ctx.guild else None,
                channel_id=ctx.channel.id,
                is_slash=False,
                failed=True,
            )
        except Exception:
            pass

        try:
            if isinstance(error, CommandNotFound):
                if isinstance(self.error_channel, discord.TextChannel):
                    await self.error_channel.send(
                        f"------\nCommand not found:\n{ctx.author}, {ctx.author.id}, {ctx.channel}, {ctx.channel.id}, "
                        f"{ctx.guild}, {ctx.guild.id}, \n{ctx.message.content}\n{ctx.message.jump_url}\n------")
                logger.warning(f"Command not found: {ctx.message.content}")

            elif isinstance(error, CommandOnCooldown):
                if isinstance(ctx.channel, discord.TextChannel):
                    await ctx.send(f"This command is on cooldown. Try again in {round(error.retry_after)} seconds.")
                logger.info(f"Command on cooldown: {ctx.message.content}")

            elif isinstance(error, (MissingPermissions, NotOwner)):
                quotes = [
                    "The only way to do great work is to love what you do. — Steve Jobs",
                    "In the middle of difficulty lies opportunity. — Albert Einstein",
                    "Be yourself; everyone else is already taken. — Oscar Wilde",
                    "Not all those who wander are lost. — J.R.R. Tolkien",
                    "The best time to plant a tree was 20 years ago. The second best time is now. — Chinese Proverb",
                    "It does not matter how slowly you go as long as you do not stop. — Confucius",
                    "Everything you can imagine is real. — Pablo Picasso",
                    "Turn your wounds into wisdom. — Oprah Winfrey",
                    "The mind is everything. What you think you become. — Buddha",
                    "Strive not to be a success, but rather to be of value. — Albert Einstein",
                    "What we achieve inwardly will change outer reality. — Plutarch",
                    "Happiness is not something ready made. It comes from your own actions. — Dalai Lama",
                    "The best revenge is massive success. — Frank Sinatra",
                    "If you want to lift yourself up, lift up someone else. — Booker T. Washington",
                    "Whoever is happy will make others happy too. — Anne Frank",
                    "Life is what happens when you're busy making other plans. — John Lennon",
                    "The purpose of our lives is to be happy. — Dalai Lama",
                    "Get busy living or get busy dying. — Stephen King",
                    "You only live once, but if you do it right, once is enough. — Mae West",
                    "Many of life's failures are people who did not realize how close they were to success when they gave up. — Thomas Edison",
                    "The future belongs to those who believe in the beauty of their dreams. — Eleanor Roosevelt",
                    "It is during our darkest moments that we must focus to see the light. — Aristotle",
                    "Do what you can, with what you have, where you are. — Theodore Roosevelt",
                    "Nothing is impossible, the word itself says 'I'm possible'! — Audrey Hepburn",
                    "The only impossible journey is the one you never begin. — Tony Robbins",
                    "Success is not final, failure is not fatal: it is the courage to continue that counts. — Winston Churchill",
                    "Believe you can and you're halfway there. — Theodore Roosevelt",
                    "Act as if what you do makes a difference. It does. — William James",
                    "What you get by achieving your goals is not as important as what you become by achieving your goals. — Zig Ziglar",
                    "You miss 100% of the shots you don't take. — Wayne Gretzky",
                ]
                quote = random.choice(quotes)
                await ctx.send(
                    f"You don't have permission to use that command. "
                    f"Please contact <@{OWNER_ID}> for any trouble.\n\n*{quote}*"
                )

            else:
                logger.error(f'Unhandled error: {error} in command {ctx.command}')
                if isinstance(ctx.channel, discord.TextChannel):
                    await ctx.send("An unexpected error occurred. Please try again later.")
        except discord.HTTPException:
            pass

    async def on_command_completion(self, ctx):
        logger.info(f'Command {ctx.command} completed successfully by {ctx.author} in {ctx.guild}.')
        try:
            cog_name = type(ctx.cog).__name__ if ctx.cog else None
            await self.db.record_command(
                command_name=str(ctx.command),
                cog_name=cog_name,
                user_id=ctx.author.id,
                guild_id=ctx.guild.id if ctx.guild else None,
                channel_id=ctx.channel.id,
                is_slash=False,
            )
        except Exception as e:
            logger.debug(f"Failed to record command metric: {e}")

# Initialize and run
bot = Hablemos(prefix)
bot.run(bot_token)

