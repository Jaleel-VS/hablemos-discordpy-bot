"""Bot entrypoint — Hablemos subclass of discord.py Bot."""
import logging

import discord
from discord import Game
from discord.ext.commands import Bot

from cogs.utils.discovery import discover_extensions
from config import load_settings
from db import Database
from logger import setup_logging

# Configure logging before anything else
setup_logging()
logger = logging.getLogger(__name__)

settings = load_settings()
logger.info("Environment: %s", settings.environment)



class Hablemos(Bot):

    def __init__(self, prefix, settings):
        intents = discord.Intents(
            guilds=True,
            members=True,
            messages=True,
            message_content=True,
            presences=True,
            reactions=True,
        )
        super().__init__(description="Bot by Jaleel#6408",
                          command_prefix=prefix,
                          owner_id=settings.owner_id,
                          help_command=None,
                          intents=intents,
                          )

        self.settings = settings
        self.online_channel = None
        self.error_channel = None
        self.db = Database(settings.database_url)

    async def close(self):
        await self.db.close()
        await super().close()

    async def setup_hook(self):
        try:
            await self.db.connect()
            logger.info("Database connected successfully")
        except Exception as e:
            logger.error("Failed to connect to database: %s", e)
            return

        # Load disabled cogs set for filtering
        try:
            disabled = await self.db.get_disabled_cogs()
        except Exception:
            disabled = set()

        for ext in discover_extensions():
            if ext in disabled:
                logger.info("Skipping disabled extension: %s", ext)
                continue
            try:
                await self.load_extension(ext)
                logger.info("Loaded extension: %s", ext)
            except Exception:
                logger.error("Failed to load extension %s", ext, exc_info=True)

    async def on_ready(self):
        guild_id = self.settings.bot_playground_guild_id
        guild = self.get_guild(guild_id)

        if guild is None:
            logger.warning("Guild with ID %s not found", guild_id)
            return

        self.error_channel = guild.get_channel(self.settings.error_channel_id)
        self.online_channel = guild.get_channel(self.settings.online_channel_id)

        logger.info("BOT LOADED!")

        if isinstance(self.online_channel, discord.TextChannel):
            await self.online_channel.send("I'm online bra :smiling_imp:")

        await self.change_presence(activity=Game(f'{self.command_prefix}help'))

    async def on_command_completion(self, ctx):
        logger.info("Command %s completed successfully by %s in %s.", ctx.command, ctx.author, ctx.guild)
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
            logger.debug("Failed to record command metric: %s", e)

# Initialize and run
bot = Hablemos(settings.prefix, settings)
bot.run(settings.bot_token)
