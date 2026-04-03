"""Relay cog — owner-only message relay to other guilds/channels."""
import logging

import discord
from discord.ext import commands

from base_cog import BaseCog

logger = logging.getLogger(__name__)

# Discord snowflake IDs are 17-20 digits long
_MIN_SNOWFLAKE_LEN = 17


def _is_snowflake(value: str) -> bool:
    """Return True if value looks like a Discord snowflake ID."""
    return value.isdigit() and len(value) >= _MIN_SNOWFLAKE_LEN


class RelayCog(BaseCog):

    @commands.is_owner()
    @commands.command(name="parrot", help="Parrot a message. Usage: $parrot [guild_id] [channel_id] <message>")
    async def parrot(self, ctx: commands.Context, *, message: str | None = None):
        """
        Relays the provided message to the specified guild and channel.
        If no guild/channel IDs are given, sends to the current channel.

        Only the bot owner can use this command.
        """
        invoker = f"{ctx.author} ({ctx.author.id})"
        source_loc = f"guild={getattr(ctx.guild, 'id', 'DM')} channel={getattr(ctx.channel, 'id', 'DM')}"

        if not message or not message.strip():
            await ctx.send("❌ Usage: $parrot [guild_id] [channel_id] <message>")
            logger.warning("Parrot: missing message text from %s at %s", invoker, source_loc)
            return

        # Try to parse leading guild_id and channel_id from the message
        parts = message.split(maxsplit=2)
        target_guild_id: int | None = None
        target_channel_id: int | None = None

        if len(parts) >= 2 and _is_snowflake(parts[0]) and _is_snowflake(parts[1]):
            target_guild_id = int(parts[0])
            target_channel_id = int(parts[1])
            if len(parts) < 3:
                await ctx.send("❌ Usage: $parrot <guild_id> <channel_id> <message>")
                logger.warning("Parrot: missing message text from %s at %s", invoker, source_loc)
                return
            message = parts[2]

        # Default to current channel
        if target_guild_id is None:
            target_channel = ctx.channel
            target_guild = ctx.guild
        else:
            # Validate guild
            target_guild = self.bot.get_guild(target_guild_id)
            if target_guild is None:
                logger.error(
                    "Parrot failed: bot not in target guild or guild not cached (guild_id=%s)",
                    target_guild_id,
                )
                await ctx.send("❌ I am not in that guild or cannot access it.")
                return

            # Validate channel
            target_channel = target_guild.get_channel(target_channel_id) or self.bot.get_channel(target_channel_id)
            if target_channel is None:
                logger.error(
                    "Parrot failed: target channel not found (guild_id=%s, channel_id=%s)",
                    target_guild_id, target_channel_id,
                )
                await ctx.send("❌ Target channel not found in that guild.")
                return

        if not isinstance(target_channel, discord.TextChannel):
            logger.error(
                "Parrot failed: target is not a text channel (channel_id=%s, type=%s)",
                target_channel.id, type(target_channel),
            )
            await ctx.send("❌ Target channel must be a text channel.")
            return

        logger.info(
            "Parrot invoked by %s from %s → target_guild=%s target_channel=%s",
            invoker, source_loc, getattr(target_guild, "id", "DM"), target_channel.id,
        )

        # Permission check: can the bot send messages in the target channel?
        if target_guild is not None:
            perms = target_channel.permissions_for(target_guild.me)
            if not perms.send_messages:
                logger.error(
                    "Parrot failed: missing permission to send in target channel (channel_id=%s)",
                    target_channel.id,
                )
                await ctx.send("❌ I don't have permission to send messages in the target channel.")
                return

        try:
            await target_channel.send(message)
            if target_channel.id != ctx.channel.id:
                await ctx.send(
                    f"✅ Sent to #{target_channel.name} ({target_channel.id})."
                )
            logger.info(
                "Parrot succeeded: relayed message from %s to channel=%s",
                invoker, target_channel.id,
            )
        except discord.Forbidden:
            logger.exception(
                "Parrot exception: Forbidden sending to channel=%s",
                target_channel.id,
            )
            await ctx.send("❌ Forbidden: I cannot send a message there.")
        except discord.HTTPException:
            logger.exception(
                "Parrot exception: HTTPException sending to channel=%s",
                target_channel.id,
            )
            await ctx.send("❌ Failed to send due to an HTTP error.")
        except Exception:
            logger.exception(
                "Parrot exception: Unexpected error sending to channel=%s",
                target_channel.id,
            )
            await ctx.send("❌ An unexpected error occurred while sending the message.")

async def setup(bot: commands.Bot):
    await bot.add_cog(RelayCog(bot))

