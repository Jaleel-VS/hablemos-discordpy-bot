"""
Tomatoes Cog
Throw tomatoes at people.
"""

from io import BytesIO
import logging
from PIL import Image
from discord import File, Message
from discord.ext.commands import BucketType, Context, command, cooldown
from base_cog import BaseCog
from discord.ext import commands

from cogs.tomatoes_cog.generator import generate_tomatoes
from cogs.utils.embeds import red_embed

logger = logging.getLogger(__name__)

class TomatoesCog(BaseCog):
    """Throw tomatoes at people."""

    @command(aliases=['tomatoes'])
    @cooldown(1, 5, type=BucketType.user)
    async def tomato(self, ctx: Context, *user_input):
        """
        Throws tomatoes at a user.

        Example usage:
        `$tomato @Pablo`
        `$tomato @Rai`
        Or reply to a message with `$tomato`
        """
        user = None
        
        if len(ctx.message.mentions) > 0:
            user = ctx.message.mentions[0]
        elif ctx.message.reference != None:
            resolved_message = ctx.message.reference.resolved

            if isinstance(resolved_message, Message):
                user = resolved_message.author

        if user == None:
            await ctx.send(embed=red_embed(f"Please type `$help tomato` for info on correct usage."))
            return
        
        profile_picture = user.display_avatar.with_size(512)
        data = BytesIO(await profile_picture.read())
        base = Image.open(data).convert("RGBA")
        output_path = generate_tomatoes(base)
        await ctx.send(content = user.mention, file=File(output_path))

async def setup(bot):
    """Setup function to add the cog to the bot"""
    await bot.add_cog(TomatoesCog(bot))
    logger.info("TomatoesCog loaded successfully")