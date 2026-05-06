"""Bot entrypoint — Hablemos subclass of discord.py Bot."""
from __future__ import annotations

import asyncio
import logging

import discord
from discord import Game
from discord.ext.commands import Bot

from cogs.utils.discovery import discover_extensions
from config import Settings, load_settings
from db import Database
from logger import setup_logging

# Configure logging before anything else.
setup_logging()
logger = logging.getLogger(__name__)


class Hablemos(Bot):
    """Main Hablemos bot client."""

    def __init__(self, prefix: str, settings: Settings):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        intents.presences = True

        super().__init__(
            description="Hablemos language learning bot",
            command_prefix=prefix,
            owner_id=settings.owner_id,
            help_command=None,
            intents=intents,
        )

        self.settings = settings
        self.online_channel: discord.TextChannel | None = None
        self.error_channel: discord.TextChannel | None = None
        self.db = Database(settings.database_url)
        self._announced_ready = False

    async def close(self) -> None:
        """Close database and Discord resources."""
        try:
            await self.db.close()
        finally:
            await super().close()

    async def setup_hook(self) -> None:
        """Connect database and load extensions."""
        for attempt in range(5):
            try:
                await self.db.connect()
                logger.info("Database connected successfully")
                break
            except Exception:
                logger.warning(
                    "DB not ready, attempt %s/5",
                    attempt + 1,
                    exc_info=True,
                )
                if attempt < 4:
                    await asyncio.sleep(2**attempt)
        else:
            logger.critical("Database unavailable after 5 retries — shutting down")
            await self.close()
            raise RuntimeError("Database unavailable after 5 retries")

        try:
            disabled = await self.db.get_disabled_cogs()
        except Exception:
            logger.exception(
                "Failed to load disabled cogs; continuing with all cogs enabled"
            )
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

    async def on_ready(self) -> None:
        """Handle the bot ready event."""
        guild_id = self.settings.bot_playground_guild_id
        guild = self.get_guild(guild_id)

        if guild is None:
            logger.warning("Guild with ID %s not found", guild_id)
            return

        error_channel = guild.get_channel(self.settings.error_channel_id)
        online_channel = guild.get_channel(self.settings.online_channel_id)

        self.error_channel = (
            error_channel if isinstance(error_channel, discord.TextChannel) else None
        )
        self.online_channel = (
            online_channel if isinstance(online_channel, discord.TextChannel) else None
        )

        logger.info("Bot ready as %s", self.user)

        if not self._announced_ready and self.online_channel is not None:
            await self.online_channel.send("Hablemos is online.")
            self._announced_ready = True

        await self.change_presence(activity=Game(f"{self.command_prefix}help"))

    async def on_command_completion(self, ctx) -> None:
        """Record successful prefix command usage."""
        logger.info(
            "Command %s completed successfully by %s in %s.",
            ctx.command,
            ctx.author,
            ctx.guild,
        )
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
        except Exception:
            logger.debug("Failed to record command metric", exc_info=True)

    async def on_app_command_completion(self, interaction, command) -> None:
        """Record successful slash command usage."""
        logger.info(
            "Slash command %s completed by %s in %s.",
            command.qualified_name,
            interaction.user,
            interaction.guild,
        )
        try:
            await self.db.record_command(
                command_name=command.qualified_name,
                cog_name=type(command.binding).__name__ if command.binding else None,
                user_id=interaction.user.id,
                guild_id=interaction.guild_id,
                channel_id=interaction.channel_id,
                is_slash=True,
            )
        except Exception:
            logger.debug("Failed to record slash command metric", exc_info=True)


def main() -> None:
    """Load settings and run the bot."""
    settings = load_settings()
    logger.info("Environment: %s", settings.environment)

    bot = Hablemos(settings.prefix, settings)
    bot.run(settings.bot_token)


if __name__ == "__main__":
    main()
