from discord.ext.commands import Cog, CommandOnCooldown, CommandError
from discord.ext.commands import Bot

COLORS = [0x57F287, 0xED4245, 0xEB459E, 0xFEE75C, 0xf47fff, 0x7289da, 0xe74c3c,
          0xe67e22, 0xf1c40f, 0xe91e63, 0x9b59b6,
          0x3498db, 0x2ecc71, 0x1abc9c, ]

class BaseCog(Cog):
    """Base class for all cogs"""
    def __init__(self, bot):
        self.bot: Bot = bot

    async def cog_command_error(self, ctx, error):
        """Handle errors for commands in this cog"""
        if isinstance(error, CommandOnCooldown):
            await ctx.send(f"⏱️ Command is on cooldown. Try again in {error.retry_after:.1f} seconds.")
        else:
            print(f'An error occurred: {error} in {ctx.channel}')
            # Re-raise other errors so they can be handled by global error handlers
            raise error
