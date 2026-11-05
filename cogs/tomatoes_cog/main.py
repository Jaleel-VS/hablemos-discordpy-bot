"""
Tomatoes Cog
Throw tomatoes at people.
"""

import logging
import tempfile
from io import BytesIO
from pathlib import Path

from discord import File, Forbidden, HTTPException, Message
from discord.ext.commands import BucketType, Context, command, cooldown
from PIL import Image

from base_cog import BaseCog
from cogs.tomatoes_cog.generator import generate_tomatoes
from cogs.utils.embeds import red_embed

logger = logging.getLogger(__name__)

def _target_user(ctx: Context):
    """Mention in the command text, else the replied-to author."""
    for user in ctx.message.mentions:
        if user.mention in ctx.message.content:
            return user
    resolved = ctx.message.reference.resolved if ctx.message.reference else None
    if isinstance(resolved, Message):
        return resolved.author
    return None


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
        output_path = None

        try:
            user = _target_user(ctx)
            if user is None:
                await ctx.send(embed=red_embed("Please type `$help tomato` for info on correct usage."))
                return

            profile_picture = user.display_avatar.with_size(512)
            image = Image.open(BytesIO(await profile_picture.read()))
            base = image.convert("RGBA")

            with tempfile.NamedTemporaryFile(suffix=".webp", delete=False) as tmp:
                output_path = tmp.name

            output_path = generate_tomatoes(base, output_path)
            await ctx.send(content = user.mention, file=File(output_path))
        except Forbidden:
            logger.warning(
                "Missing permissions to send tomatoes image in channel %s (guild %s)",
                ctx.channel.id,
                ctx.guild.id if ctx.guild else "DM",
            )
        except HTTPException:
            logger.exception("Failed to send tomatoes image")
            try:
                await ctx.send(embed=red_embed("Something went wrong sending the image."))
            except Forbidden:
                logger.warning("Also missing permissions to send error embed in channel %s", ctx.channel.id)
        except Exception:
            logger.exception("Failed to generate tomatoes image")
            try:
                await ctx.send(embed=red_embed("Something went wrong generating the image."))
            except Forbidden:
                logger.warning("Missing permissions to send error embed in channel %s", ctx.channel.id)
        finally:
            if output_path:
                Path(output_path).unlink(missing_ok=True)


async def setup(bot):
    """Setup function to add the cog to the bot"""
    await bot.add_cog(TomatoesCog(bot))
    logger.info("TomatoesCog loaded successfully")
