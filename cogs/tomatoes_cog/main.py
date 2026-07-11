"""
Tomatoes Cog
Throw tomatoes at people.
"""

import logging
from io import BytesIO
from pathlib import Path

from discord import File, Forbidden, HTTPException, Message
from discord.ext.commands import BucketType, Context, command, cooldown
from PIL import Image

from base_cog import BaseCog
from cogs.tomatoes_cog.generator import generate_tomatoes
from cogs.tomatoes_cog.generator_v2 import generate_tomatoes_v2
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
        output_path = None
        try:
            user = None

            if len(ctx.message.mentions) > 0:
                user = ctx.message.mentions[0]
            elif ctx.message.reference is not None:
                resolved_message = ctx.message.reference.resolved

                if isinstance(resolved_message, Message):
                    user = resolved_message.author

            if user is None:
                await ctx.send(embed=red_embed("Please type `$help tomato` for info on correct usage."))
                return

            profile_picture = user.display_avatar.with_size(512)
            data = BytesIO(await profile_picture.read())
            base = Image.open(data).convert("RGBA")
            output_path = generate_tomatoes(base)
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

    @command(aliases=["t2"])
    @cooldown(1, 5, type=BucketType.user)
    async def tomato2(self, ctx: Context, *user_input):
        """Throws tomatoes AGGRESSIVELY at a user (v2).

        Example usage:
        `$tomato2 @Pablo`
        `$t2 @Rai`
        Or reply to a message with `$tomato2`
        """
        try:
            user = None

            if len(ctx.message.mentions) > 0:
                user = ctx.message.mentions[0]
            elif ctx.message.reference is not None:
                resolved_message = ctx.message.reference.resolved
                if isinstance(resolved_message, Message):
                    user = resolved_message.author

            if user is None:
                await ctx.send(embed=red_embed("Mention someone or reply to a message! `$t2 @user`"))
                return

            async with ctx.typing():
                pfp = user.display_avatar.with_size(512)
                data = BytesIO(await pfp.read())
                avatar = Image.open(data).convert("RGBA")
                gif_buf = generate_tomatoes_v2(avatar)

            await ctx.send(
                content=user.mention,
                file=File(gif_buf, filename="tomatoes.gif"),
            )
        except Forbidden:
            logger.warning(
                "Missing permissions to send tomatoes in channel %s (guild %s)",
                ctx.channel.id,
                ctx.guild.id if ctx.guild else "DM",
            )
        except HTTPException:
            logger.exception("Failed to send tomatoes v2 image")
            try:
                await ctx.send(embed=red_embed("Something went wrong sending the image."))
            except Forbidden:
                logger.warning("Missing permissions to send error embed in channel %s", ctx.channel.id)
        except Exception:
            logger.exception("Failed to generate tomatoes v2 image")
            try:
                await ctx.send(embed=red_embed("Something went wrong generating the image."))
            except Forbidden:
                logger.warning("Missing permissions to send error embed in channel %s", ctx.channel.id)

async def setup(bot):
    """Setup function to add the cog to the bot"""
    await bot.add_cog(TomatoesCog(bot))
    logger.info("TomatoesCog loaded successfully")
