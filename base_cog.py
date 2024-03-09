from discord.ext.commands import Cog
from discord.ext.commands import Bot

COLORS = [0x57F287, 0xED4245, 0xEB459E, 0xFEE75C, 0xf47fff, 0x7289da, 0xe74c3c,
          0xe67e22, 0xf1c40f, 0xe91e63, 0x9b59b6,
          0x3498db, 0x2ecc71, 0x1abc9c, ]

class BaseCog(Cog):
    """Base class for all cogs"""
    def __init__(self, bot):
        self.bot: Bot = bot

    @staticmethod
    async def cog_command_error(ctx, error):
        print(f'An error occurred: {error} in {ctx.channel}')
