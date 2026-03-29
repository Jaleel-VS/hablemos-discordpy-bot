"""Hangman cog — manages game sessions per channel."""
import asyncio
import logging

import discord
from discord.ext import commands

from base_cog import BaseCog
from cogs.hangman_cog.hangman import Hangman
from cogs.hangman_cog.hangman_help import get_word

# Set up logger for this module
logger = logging.getLogger(__name__)

CATEGORIES = {
    'animales': 199,
    'profesiones': 141,
    'ciudades': 49
}

class HangmanController(BaseCog):
    """Classic hangman game for Spanish vocabulary practice."""

    def __init__(self, bot):
        super().__init__(bot)
        self.active_games: dict[int, Hangman] = {}  # channel_id -> game instance
        self._game_locks: dict[int, asyncio.Lock] = {}  # channel_id -> lock

    def _get_channel_lock(self, channel_id: int) -> asyncio.Lock:
        """Get or create a lock for the specified channel."""
        if channel_id not in self._game_locks:
            self._game_locks[channel_id] = asyncio.Lock()
        return self._game_locks[channel_id]

    def _is_game_active(self, channel_id: int) -> bool:
        """Check if a game is currently active in the channel."""
        return channel_id in self.active_games

    @commands.command(aliases=['hm', 'hang'])
    async def hangman(self, ctx, category: str = 'animales'):
        """
        Start a hangman game in Spanish!

        Categories:
        • `animales` (199 words) - Default
        • `profesiones` (141 words)
        • `ciudades` (49 words) - Major Spanish-speaking cities

        Usage: `$hangman <category>`
        Example: `$hangman profesiones`

        Game controls:
        • Type letters to guess
        • Type `quit` to exit (starter only)
        • Auto-exits after 45 seconds of inactivity
        """
        channel_id = ctx.channel.id
        user_id = ctx.author.id

        logger.info("Hangman command invoked by %s (%s) in channel %s (%s) with category '%s'", ctx.author, user_id, ctx.channel, channel_id, category)

        # Validate category
        if category not in CATEGORIES:
            logger.warning("Invalid category '%s' requested by %s (%s)", category, ctx.author, user_id)
            available = ', '.join(f'`{cat}` ({count})' for cat, count in CATEGORIES.items())
            return await ctx.send(f"❌ Category not found!\n\n**Available categories:**\n{available}")

        # Use lock to prevent race conditions
        async with self._get_channel_lock(channel_id):
            if self._is_game_active(channel_id):
                logger.info("Game start denied - game already active in channel %s", channel_id)
                return await ctx.send("🎮 There's already a hangman game running in this channel!")

            try:
                logger.info("Starting new hangman game in channel %s with category '%s'", channel_id, category)
                await self._start_new_game(ctx, channel_id, category)
                logger.info("Hangman game successfully started in channel %s", channel_id)
            except Exception as e:
                # Ensure cleanup on any error
                self.active_games.pop(channel_id, None)
                logger.error("Failed to start hangman game in channel %s: %s", channel_id, e, exc_info=True)
                await ctx.send("❌ Failed to start game. Please try again later.")
                raise
            # Successfully started; nothing else to send here

    async def _start_new_game(self, ctx, channel_id: int, category: str):
        """Start a new hangman game with proper cleanup."""
        try:
            # Get words for the category
            logger.debug("Getting words for category '%s'", category)
            words = get_word(category)
            if not words:
                logger.error("No words found for category: %s", category)
                return await ctx.send(f"❌ No words found for category: {category}")

            logger.debug("Selected word for game: %s (%s)", words[0], words[1] if len(words) > 1 else 'no definition')

            # Create and register the game
            game = Hangman(self.bot, words, category)
            self.active_games[channel_id] = game

            logger.info("Game registered for channel %s, starting game loop", channel_id)

            # Start the game
            await game.game_loop(ctx)

        except Exception as e:
            logger.error("Error during game execution in channel %s: %s", channel_id, e, exc_info=True)
            raise
        finally:
            # Always cleanup, even if game crashes
            if channel_id in self.active_games:
                logger.info("Cleaning up game for channel %s", channel_id)
                self.active_games.pop(channel_id, None)

            # Clean up old locks periodically to prevent memory leaks
            if channel_id in self._game_locks and not self._is_game_active(channel_id):
                logger.debug("Cleaning up lock for channel %s", channel_id)
                del self._game_locks[channel_id]

    @commands.command(name='hangman_status', aliases=['hm_status'])
    async def hangman_status(self, ctx):
        """Show active hangman games."""
        logger.info("Hangman status requested by %s in channel %s", ctx.author, ctx.channel)

        if not self.active_games:
            logger.debug("No active games found")
            return await ctx.send("🎮 No active hangman games!")

        logger.debug("Found %s active games", len(self.active_games))
        status_lines = []
        for channel_id in self.active_games:
            channel = self.bot.get_channel(channel_id)
            if channel:
                # Handle different channel types
                if isinstance(channel, discord.DMChannel):
                    recipient_name = channel.recipient.display_name if channel.recipient else "Unknown User"
                    channel_name = f"DM with {recipient_name}"
                elif isinstance(channel, discord.abc.GuildChannel):
                    channel_name = channel.name
                else:
                    channel_name = f"Channel ({channel_id})"
            else:
                channel_name = f"Unknown ({channel_id})"
            status_lines.append(f"• {channel_name}")

        status = '\n'.join(status_lines)
        await ctx.send(f"🎮 **Active Games:**\n{status}")
        logger.debug("Status response sent with %s games listed", len(status_lines))

    async def cog_unload(self):
        """Cleanup when cog is unloaded."""
        logger.info("Hangman cog unloading, cleaning up %s active games", len(self.active_games))
        # Clear all active games - the games will naturally timeout
        self.active_games.clear()
        self._game_locks.clear()
        logger.info("Hangman cog cleanup completed")

async def setup(bot):
    await bot.add_cog(HangmanController(bot))
