from discord.ext.commands import Cog, CommandOnCooldown
from discord.ext.commands import Bot
from discord import Interaction
import logging

logger = logging.getLogger(__name__)

COLORS = [0x57F287, 0xED4245, 0xEB459E, 0xFEE75C, 0xf47fff, 0x7289da, 0xe74c3c,
          0xe67e22, 0xf1c40f, 0xe91e63, 0x9b59b6,
          0x3498db, 0x2ecc71, 0x1abc9c, ]

class BaseCog(Cog):
    """Base class for all cogs"""
    def __init__(self, bot):
        self.bot: Bot = bot

    async def cog_app_command_after_invoke(self, interaction: Interaction) -> None:
        """Track slash command usage for metrics."""
        try:
            await self.bot.db.record_command(
                command_name=interaction.command.qualified_name if interaction.command else "unknown",
                cog_name=type(self).__name__,
                user_id=interaction.user.id,
                guild_id=interaction.guild_id,
                channel_id=interaction.channel_id,
                is_slash=True,
            )
        except Exception as e:
            logger.debug(f"Failed to record slash command metric: {e}")

    async def cog_command_error(self, ctx, error):
        """Handle errors for commands in this cog"""
        if isinstance(error, CommandOnCooldown):
            await ctx.send(f"⏱️ Command is on cooldown. Try again in {error.retry_after:.1f} seconds.")
        else:
            logger.error(f'An error occurred: {error} in {ctx.channel}')
            # Re-raise other errors so they can be handled by global error handlers
            raise error
