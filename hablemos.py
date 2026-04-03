"""Bot entrypoint — Hablemos subclass of discord.py Bot."""
import asyncio
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
        for attempt in range(5):
            try:
                await self.db.connect()
                logger.info("Database connected successfully")
                break
            except Exception:
                logger.warning("DB not ready, attempt %s/5", attempt + 1, exc_info=True)
                if attempt < 4:
                    await asyncio.sleep(2 ** attempt)
        else:
            logger.error("Database unavailable after 5 retries — aborting setup")
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
                await asyncio.wait_for(self.load_extension(ext), timeout=30)
                logger.info("Loaded extension: %s", ext)
            except TimeoutError:
                logger.error("Extension %s timed out during load", ext)
            except Exception:
                logger.error("Failed to load extension %s", ext, exc_info=True)

        self.tree.on_app_command_completion = self._on_app_command_completion

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

    async def _on_app_command_completion(self, interaction, command):
        logger.info("Slash command %s completed by %s in %s.", command.qualified_name, interaction.user, interaction.guild)
        try:
            await self.db.record_command(
                command_name=command.qualified_name,
                cog_name=type(command.binding).__name__ if command.binding else None,
                user_id=interaction.user.id,
                guild_id=interaction.guild_id,
                channel_id=interaction.channel_id,
                is_slash=True,
            )
        except Exception as e:
            logger.debug("Failed to record slash command metric: %s", e)

# Initialize and run
bot = Hablemos(settings.prefix, settings)
bot.run(settings.bot_token)
