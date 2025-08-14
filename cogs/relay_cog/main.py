import logging
from typing import Optional

import discord
from discord.ext import commands

from base_cog import BaseCog


logger = logging.getLogger(__name__)


class RelayCog(BaseCog):
    def __init__(self, bot: commands.Bot):
        super().__init__(bot)

    @commands.is_owner()
    @commands.command(name="parrot", help="Parrot a message to a target guild/channel by ID. Usage: $parrot <guild_id> <channel_id> <message>")
    async def parrot(self, ctx: commands.Context, target_guild_id: int, target_channel_id: int, *, message: str = None):
        """
        Relays the provided message to the specified guild and channel.

        Only the bot owner can use this command.
        """
        invoker = f"{ctx.author} ({ctx.author.id})"
        source_loc = f"guild={getattr(ctx.guild, 'id', 'DM')} channel={getattr(ctx.channel, 'id', 'DM')}"

        if not message or not message.strip():
            await ctx.send("❌ Usage: $parrot <guild_id> <channel_id> <message>")
            logger.warning(f"Parrot: missing message text from {invoker} at {source_loc}")
            return

        logger.info(
            f"Parrot invoked by {invoker} from {source_loc} → target_guild={target_guild_id} target_channel={target_channel_id}"
        )

        # Validate guild
        target_guild: Optional[discord.Guild] = self.bot.get_guild(target_guild_id)
        if target_guild is None:
            # The bot is not in the guild or not cached
            logger.error(
                f"Parrot failed: bot not in target guild or guild not cached (guild_id={target_guild_id})"
            )
            await ctx.send("❌ I am not in that guild or cannot access it.")
            return

        # Validate channel
        target_channel = target_guild.get_channel(target_channel_id) or self.bot.get_channel(target_channel_id)
        if target_channel is None:
            logger.error(
                f"Parrot failed: target channel not found (guild_id={target_guild_id}, channel_id={target_channel_id})"
            )
            await ctx.send("❌ Target channel not found in that guild.")
            return

        if not isinstance(target_channel, discord.TextChannel):
            logger.error(
                f"Parrot failed: target is not a text channel (guild_id={target_guild_id}, channel_id={target_channel_id}, type={type(target_channel)})"
            )
            await ctx.send("❌ Target channel must be a text channel.")
            return

        # Permission check: can the bot send messages in the target channel?
        perms = target_channel.permissions_for(target_guild.me)
        if not perms.send_messages:
            logger.error(
                f"Parrot failed: missing permission to send in target channel (guild_id={target_guild_id}, channel_id={target_channel_id})"
            )
            await ctx.send("❌ I don't have permission to send messages in the target channel.")
            return

        try:
            await target_channel.send(message)
            await ctx.send(
                f"✅ Sent to `{target_guild.name}` #{target_channel.name} ({target_guild_id}/{target_channel_id})."
            )
            logger.info(
                f"Parrot succeeded: relayed message from {invoker} to guild={target_guild_id} channel={target_channel_id}"
            )
        except discord.Forbidden:
            logger.exception(
                f"Parrot exception: Forbidden sending to guild={target_guild_id} channel={target_channel_id}"
            )
            await ctx.send("❌ Forbidden: I cannot send a message there.")
        except discord.HTTPException as e:
            logger.exception(
                f"Parrot exception: HTTPException sending to guild={target_guild_id} channel={target_channel_id}: {e}"
            )
            await ctx.send("❌ Failed to send due to an HTTP error.")
        except Exception as e:
            logger.exception(
                f"Parrot exception: Unexpected error sending to guild={target_guild_id} channel={target_channel_id}: {e}"
            )
            await ctx.send("❌ An unexpected error occurred while sending the message.")


async def setup(bot: commands.Bot):
    await bot.add_cog(RelayCog(bot))


