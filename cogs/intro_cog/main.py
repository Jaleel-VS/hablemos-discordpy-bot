"""Introduction tracker — enforces a cooldown on the introductions channel."""
from discord.ext import commands
from discord.ext.commands import Bot, has_permissions, Cog
from base_cog import BaseCog
from cogs.utils.embeds import green_embed, red_embed, yellow_embed
from discord import Embed, Color, HTTPException, Forbidden, NotFound, Member, Message
from .config import (
    INTRO_COOLDOWN_DAYS,
    DEFAULT_WARN_CHANNEL_ID, DEFAULT_ALERT_CHANNEL_ID,
    SETTING_WARN_CHANNEL, SETTING_ALERT_CHANNEL,
    EXEMPT_ROLE_IDS,
)
import logging

logger = logging.getLogger(__name__)


def ordinal(n: int) -> str:
    """Return ordinal string for a number (1st, 2nd, 3rd, etc.)."""
    if 11 <= (n % 100) <= 13:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
    return f"{n}{suffix}"


def _build_alert_embed(
    author: Member, user_id: int, attempt_count: int, content: str, *, deleted: bool = True,
) -> Embed:
    """Build the staff alert embed for a duplicate introduction."""
    title = "Duplicate Introduction Removed" if deleted else "Duplicate Introduction (delete failed)"
    embed = Embed(title=title, color=Color(0xE67E22))
    embed.add_field(name="User", value=f"{author.mention} (`{user_id}`)", inline=True)
    embed.add_field(
        name="Attempt",
        value=f"This was their **{ordinal(attempt_count)}** introduction attempt",
        inline=True,
    )
    embed.add_field(name="Message Content", value=content[:1024], inline=False)
    return embed


class IntroductionTracker(BaseCog):
    def __init__(self, bot: Bot):
        super().__init__(bot)
        self.intro_channel_id = bot.settings.intro_channel_id
        self.general_channel_id = bot.settings.general_channel_id
        self._exempt_users: set[int] = set()

    async def cog_load(self) -> None:
        """Cache exempt users from DB on cog load."""
        self._exempt_users = await self.bot.db.get_intro_exempt_users()

    # ── Helpers ──

    async def _get_channel_id(self, setting_key: str, default: int) -> int:
        """Get a configurable channel ID from DB, falling back to default."""
        channel_id = await self.bot.db.get_bot_setting(setting_key)
        return channel_id if channel_id is not None else default

    def _is_exempt(self, member: Member) -> bool:
        """Check if a member is exempt via role or user exemption list."""
        if member.id in self._exempt_users:
            return True
        return any(role.id in EXEMPT_ROLE_IDS for role in getattr(member, 'roles', []))

    async def _handle_duplicate_intro(self, message: Message, attempt_count: int) -> None:
        """Delete a duplicate intro, warn the user, and alert staff."""
        saved_content = message.content or "(no text content)"

        # Attempt to delete — continue to warn/alert even on failure
        deleted = True
        try:
            await message.delete()
            logger.info(f"Deleted duplicate introduction from {message.author} ({message.author.id})")
        except (Forbidden, NotFound) as e:
            deleted = False
            logger.warning(f"Could not delete duplicate intro from {message.author}: {e}")
        except HTTPException:
            deleted = False
            logger.exception(f"HTTP error deleting duplicate intro from {message.author}")

        # Warn the user
        warn_channel_id = await self._get_channel_id(SETTING_WARN_CHANNEL, DEFAULT_WARN_CHANNEL_ID)
        warn_channel = self.bot.get_channel(warn_channel_id)
        if warn_channel:
            try:
                await warn_channel.send(
                    content=f"Hey {message.author.mention}! 👋",
                    embed=yellow_embed(
                        f"We noticed you tried to post another introduction. "
                        f"You've already introduced yourself recently, so we removed your duplicate message.\n\n"
                        f"Feel free to chat with everyone in <#{self.general_channel_id}> instead! "
                        f"We'd love to hear from you there. 😊"
                    ),
                )
            except HTTPException:
                logger.exception("Failed to send intro warning to warn channel")

        # Alert staff
        alert_channel_id = await self._get_channel_id(SETTING_ALERT_CHANNEL, DEFAULT_ALERT_CHANNEL_ID)
        alert_channel = self.bot.get_channel(alert_channel_id)
        if alert_channel:
            try:
                embed = _build_alert_embed(
                    message.author, message.author.id, attempt_count, saved_content, deleted=deleted,
                )
                await alert_channel.send(embed=embed)
            except HTTPException:
                logger.exception("Failed to send intro alert to staff channel")

    # ── Listener ──

    @Cog.listener()
    async def on_message(self, message: Message):
        """Listen for messages in the introduction channel."""
        if message.author.bot or message.channel.id != self.intro_channel_id:
            return

        try:
            is_enabled = await self.bot.db.get_feature_setting('intro_tracker')
            if not is_enabled:
                return

            if self._is_exempt(message.author):
                logger.debug(f"User {message.author} ({message.author.id}) is exempt from intro tracking")
                return

            existing = await self.bot.db.check_user_introduction(message.author.id, INTRO_COOLDOWN_DAYS)

            if existing:
                await self.bot.db.record_introduction(message.author.id)
                attempt_count = await self.bot.db.get_introduction_count(message.author.id)
                await self._handle_duplicate_intro(message, attempt_count)
            else:
                await self.bot.db.record_introduction(message.author.id)
                logger.info(f"Recorded introduction from {message.author} ({message.author.id})")

        except Exception:
            logger.exception(f"Unhandled error in introduction tracker for {message.author}")

    # ── Commands ──

    @commands.group(name='introtracker', aliases=['toggleintro'], invoke_without_command=True)
    @has_permissions(manage_messages=True)
    async def introtracker(self, ctx: commands.Context):
        """Introduction tracker management. Use subcommands: on, off, status, alertchannel, warnchannel."""
        await ctx.invoke(self.status)

    @introtracker.command(name='on', aliases=['enable'])
    @has_permissions(manage_messages=True)
    async def on_cmd(self, ctx: commands.Context):
        """Enable the introduction tracker."""
        await self.bot.db.set_feature_setting('intro_tracker', True)
        await ctx.send(embed=green_embed("Introduction tracker **enabled** ✅"))
        logger.info(f"Introduction tracker enabled by {ctx.author}")

    @introtracker.command(name='off', aliases=['disable'])
    @has_permissions(manage_messages=True)
    async def off_cmd(self, ctx: commands.Context):
        """Disable the introduction tracker."""
        await self.bot.db.set_feature_setting('intro_tracker', False)
        await ctx.send(embed=red_embed("Introduction tracker **disabled** ❌"))
        logger.info(f"Introduction tracker disabled by {ctx.author}")

    @introtracker.command(name='status')
    @has_permissions(manage_messages=True)
    async def status(self, ctx: commands.Context):
        """Show introduction tracker status and statistics."""
        is_enabled = await self.bot.db.get_feature_setting('intro_tracker')
        warn_channel_id = await self._get_channel_id(SETTING_WARN_CHANNEL, DEFAULT_WARN_CHANNEL_ID)
        alert_channel_id = await self._get_channel_id(SETTING_ALERT_CHANNEL, DEFAULT_ALERT_CHANNEL_ID)
        stats = await self.bot.db.get_introduction_stats(INTRO_COOLDOWN_DAYS)

        embed = Embed(title="Introduction Tracker Status", color=Color(0x3498DB))
        embed.add_field(name="Status", value="Enabled ✅" if is_enabled else "Disabled ❌", inline=False)
        embed.add_field(name="Cooldown", value=f"{INTRO_COOLDOWN_DAYS} days", inline=True)
        embed.add_field(name="Watched Channel", value=f"<#{self.intro_channel_id}>", inline=True)
        embed.add_field(name="Warn Channel", value=f"<#{warn_channel_id}>", inline=True)
        embed.add_field(name="Alert Channel", value=f"<#{alert_channel_id}>", inline=True)
        embed.add_field(name="Redirect Channel", value=f"<#{self.general_channel_id}>", inline=True)
        embed.add_field(name="Total Introductions", value=str(stats["total"]), inline=True)
        embed.add_field(name="Unique Users", value=str(stats["unique_users"]), inline=True)
        embed.add_field(name="Recent", value=f"{stats['recent']} ({INTRO_COOLDOWN_DAYS}d)", inline=True)
        await ctx.send(embed=embed)

    @introtracker.command(name='alertchannel')
    @has_permissions(manage_messages=True)
    async def alertchannel(self, ctx: commands.Context):
        """Set the staff alert channel. Usage: $introtracker alertchannel #channel"""
        if not ctx.message.channel_mentions:
            await ctx.send(embed=red_embed("Usage: `$introtracker alertchannel #channel`"))
            return
        channel = ctx.message.channel_mentions[0]
        await self.bot.db.set_bot_setting(SETTING_ALERT_CHANNEL, channel.id)
        await ctx.send(embed=green_embed(f"Staff alert channel set to {channel.mention} ✅"))
        logger.info(f"Intro alert channel set to {channel.id} by {ctx.author}")

    @introtracker.command(name='warnchannel')
    @has_permissions(manage_messages=True)
    async def warnchannel(self, ctx: commands.Context):
        """Set the user warning channel. Usage: $introtracker warnchannel #channel"""
        if not ctx.message.channel_mentions:
            await ctx.send(embed=red_embed("Usage: `$introtracker warnchannel #channel`"))
            return
        channel = ctx.message.channel_mentions[0]
        await self.bot.db.set_bot_setting(SETTING_WARN_CHANNEL, channel.id)
        await ctx.send(embed=green_embed(f"User warning channel set to {channel.mention} ✅"))
        logger.info(f"Intro warn channel set to {channel.id} by {ctx.author}")

    @commands.command(aliases=['clearintro'])
    @has_permissions(manage_messages=True)
    async def resetintro(self, ctx: commands.Context, user_id: int | None = None):
        """Clear a user's introduction history so they can post again."""
        if user_id is None:
            await ctx.send(embed=red_embed("Usage: `$resetintro <user_id>`"))
            return
        try:
            result = await self.bot.db.clear_introductions(user_id)
            count = int(result.split()[-1]) if result else 0
            if count:
                await ctx.send(embed=green_embed(
                    f"Cleared **{count}** introduction record(s) for user `{user_id}`. They can post again."
                ))
                logger.info(f"{ctx.author} cleared {count} intro records for user {user_id}")
            else:
                await ctx.send(embed=yellow_embed(f"No introduction records found for user `{user_id}`."))
        except Exception:
            logger.exception(f"Error clearing introductions for user {user_id}")
            await ctx.send(embed=red_embed("Something went wrong. Check logs for details."))

    @commands.command()
    @has_permissions(manage_messages=True)
    async def introexempt(self, ctx: commands.Context, user_id: int | None = None):
        """Exempt a user from intro tracking. Usage: $introexempt <user_id>"""
        if user_id is None:
            await ctx.send(embed=red_embed("Usage: `$introexempt <user_id>`"))
            return
        try:
            added = await self.bot.db.add_intro_exempt_user(user_id, ctx.author.id)
            if added:
                self._exempt_users.add(user_id)
                await ctx.send(embed=green_embed(f"User `{user_id}` is now exempt from intro tracking."))
                logger.info(f"{ctx.author} exempted user {user_id} from intro tracking")
            else:
                await ctx.send(embed=yellow_embed(f"User `{user_id}` is already exempt."))
        except Exception:
            logger.exception(f"Error exempting user {user_id}")
            await ctx.send(embed=red_embed("Something went wrong. Check logs for details."))

    @commands.command()
    @has_permissions(manage_messages=True)
    async def introunexempt(self, ctx: commands.Context, user_id: int | None = None):
        """Remove a user's intro tracking exemption. Usage: $introunexempt <user_id>"""
        if user_id is None:
            await ctx.send(embed=red_embed("Usage: `$introunexempt <user_id>`"))
            return
        try:
            removed = await self.bot.db.remove_intro_exempt_user(user_id)
            if removed:
                self._exempt_users.discard(user_id)
                await ctx.send(embed=green_embed(f"User `{user_id}` is no longer exempt from intro tracking."))
                logger.info(f"{ctx.author} removed intro exemption for user {user_id}")
            else:
                await ctx.send(embed=yellow_embed(f"User `{user_id}` was not exempt."))
        except Exception:
            logger.exception(f"Error removing exemption for user {user_id}")
            await ctx.send(embed=red_embed("Something went wrong. Check logs for details."))


async def setup(bot):
    await bot.add_cog(IntroductionTracker(bot))
