"""Global command error handler cog."""
import logging
import random

import discord
from discord.ext import commands

from base_cog import BaseCog

logger = logging.getLogger(__name__)

PERMISSION_DENIED_QUOTES = [
    "The only way to do great work is to love what you do. — Steve Jobs",
    "In the middle of difficulty lies opportunity. — Albert Einstein",
    "Be yourself; everyone else is already taken. — Oscar Wilde",
    "Not all those who wander are lost. — J.R.R. Tolkien",
    "The best time to plant a tree was 20 years ago. The second best time is now. — Chinese Proverb",
    "It does not matter how slowly you go as long as you do not stop. — Confucius",
    "Everything you can imagine is real. — Pablo Picasso",
    "Turn your wounds into wisdom. — Oprah Winfrey",
    "The mind is everything. What you think you become. — Buddha",
    "Strive not to be a success, but rather to be of value. — Albert Einstein",
    "What we achieve inwardly will change outer reality. — Plutarch",
    "Happiness is not something ready made. It comes from your own actions. — Dalai Lama",
    "The best revenge is massive success. — Frank Sinatra",
    "If you want to lift yourself up, lift up someone else. — Booker T. Washington",
    "Whoever is happy will make others happy too. — Anne Frank",
    "Life is what happens when you're busy making other plans. — John Lennon",
    "The purpose of our lives is to be happy. — Dalai Lama",
    "Get busy living or get busy dying. — Stephen King",
    "You only live once, but if you do it right, once is enough. — Mae West",
    "Many of life's failures are people who did not realize how close they were to success when they gave up. — Thomas Edison",
    "The future belongs to those who believe in the beauty of their dreams. — Eleanor Roosevelt",
    "It is during our darkest moments that we must focus to see the light. — Aristotle",
    "Do what you can, with what you have, where you are. — Theodore Roosevelt",
    "Nothing is impossible, the word itself says 'I'm possible'! — Audrey Hepburn",
    "The only impossible journey is the one you never begin. — Tony Robbins",
    "Success is not final, failure is not fatal: it is the courage to continue that counts. — Winston Churchill",
    "Believe you can and you're halfway there. — Theodore Roosevelt",
    "Act as if what you do makes a difference. It does. — William James",
    "What you get by achieving your goals is not as important as what you become by achieving your goals. — Zig Ziglar",
    "You miss 100% of the shots you don't take. — Wayne Gretzky",
]


class ErrorHandler(BaseCog):
    """Global command error handler."""

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        # Ignore non-command prefixes (e.g. "$5", "$$")
        if len(ctx.message.content) > 1 and (
            ctx.message.content[1].isdigit() or ctx.message.content[-1] == self.bot.command_prefix
        ):
            return

        # Record failed command metric
        try:
            cog_name = type(ctx.cog).__name__ if ctx.cog else None
            await self.bot.db.record_command(
                command_name=str(ctx.command),
                cog_name=cog_name,
                user_id=ctx.author.id,
                guild_id=ctx.guild.id if ctx.guild else None,
                channel_id=ctx.channel.id,
                is_slash=False,
                failed=True,
            )
        except Exception:
            pass

        try:
            if isinstance(error, commands.CommandNotFound):
                error_channel = self.bot.error_channel
                if isinstance(error_channel, discord.TextChannel) and ctx.guild:
                    await error_channel.send(
                        f"------\nCommand not found:\n{ctx.author}, {ctx.author.id}, {ctx.channel}, {ctx.channel.id}, "
                        f"{ctx.guild}, {ctx.guild.id}, \n{ctx.message.content}\n{ctx.message.jump_url}\n------"
                    )
                logger.warning(
                    "Command not found: %s | guild: %s (%s) | user: %s",
                    ctx.message.content,
                    ctx.guild.name if ctx.guild else "DM",
                    ctx.guild.id if ctx.guild else "N/A",
                    ctx.author.id,
                )

            elif isinstance(error, commands.CommandOnCooldown):
                if isinstance(ctx.channel, discord.TextChannel):
                    await ctx.send(f"This command is on cooldown. Try again in {round(error.retry_after)} seconds.")
                logger.info("Command on cooldown: %s", ctx.message.content)

            elif isinstance(error, (commands.MissingPermissions, commands.NotOwner)):
                quote = random.choice(PERMISSION_DENIED_QUOTES)
                owner_id = self.bot.settings.owner_id
                await ctx.send(
                    f"You don't have permission to use that command. "
                    f"Please contact <@{owner_id}> for any trouble.\n\n*{quote}*"
                )

            else:
                logger.error("Unhandled error: %s in command %s", error, ctx.command)
                if isinstance(ctx.channel, discord.TextChannel):
                    await ctx.send("An unexpected error occurred. Please try again later.")
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(ErrorHandler(bot))
