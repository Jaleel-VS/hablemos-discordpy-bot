from discord.ext.commands import command, Bot, is_owner, Cog
from base_cog import BaseCog
from discord import Embed, Color, Message, TextChannel
import logging

# Channel IDs
INTRO_CHANNEL_ID = 399713966781235200  # Channel to watch for introductions
GENERAL_CHANNEL_ID = 296491080881537024  # General chat channel to redirect users to

# Default configurable channel IDs (used if not set in DB)
DEFAULT_WARN_CHANNEL_ID = 247135634265735168  # Channel to notify users about violations
DEFAULT_ALERT_CHANNEL_ID = 297877202538594304  # Staff alert channel for duplicate attempts

# DB setting keys
SETTING_WARN_CHANNEL = 'intro_warn_channel'
SETTING_ALERT_CHANNEL = 'intro_alert_channel'

# Exemptions - Users and roles that can post multiple times
EXEMPT_ROLE_IDS = (
    643097537850376199, #Rai
    243854949522472971, #Admin
    1014256322436415580, # Retired Mod
    258819531193974784, # Server Staff
    591745589054668817, # Trail Staff Helper
    1082402633979011082 # Retired Staff
)

EXEMPT_USER_IDS = (
    202995638860906496, # Ryan
)


def green_embed(text):
    return Embed(description=text, color=Color(int('00ff00', 16)))


def red_embed(text):
    return Embed(description=text, color=Color(int('e74c3c', 16)))


def yellow_embed(text):
    return Embed(description=text, color=Color(int('f1c40f', 16)))


def ordinal(n: int) -> str:
    """Return ordinal string for a number (1st, 2nd, 3rd, etc.)"""
    if 11 <= (n % 100) <= 13:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
    return f"{n}{suffix}"


class IntroductionTracker(BaseCog):
    def __init__(self, bot: Bot):
        super().__init__(bot)

    async def _get_channel_id(self, setting_key: str, default: int) -> int:
        """Get a configurable channel ID from DB, falling back to default"""
        channel_id = await self.bot.db.get_bot_setting(setting_key)
        return channel_id if channel_id is not None else default

    @Cog.listener()
    async def on_message(self, message: Message):
        """Listen for messages in the introduction channel"""
        # Ignore bot messages
        if message.author.bot:
            return

        # Only process messages in the intro channel
        if message.channel.id != INTRO_CHANNEL_ID:
            return

        # Check if feature is enabled
        try:
            is_enabled = await self.bot.db.get_feature_setting('intro_tracker')
            if not is_enabled:
                return

            user_id = message.author.id

            # Check if user is exempt
            if user_id in EXEMPT_USER_IDS:
                logging.info(f"User {message.author} ({user_id}) is exempt from intro tracking")
                return

            # Check if user has any exempt roles
            if hasattr(message.author, 'roles'):
                user_role_ids = [role.id for role in message.author.roles]
                if any(role_id in EXEMPT_ROLE_IDS for role_id in user_role_ids):
                    logging.info(f"User {message.author} ({user_id}) has exempt role, skipping intro tracking")
                    return

            # Check if user has already posted an introduction in the last 90 days
            existing_intro = await self.bot.db.check_user_introduction(user_id)

            if existing_intro:
                # Save the message content before deleting
                saved_content = message.content or "(no text content)"

                # Record this attempt before deleting
                await self.bot.db.record_introduction(user_id)
                attempt_count = await self.bot.db.get_introduction_count(user_id)

                # Delete the duplicate message
                try:
                    await message.delete()
                    logging.info(f"Deleted duplicate introduction from {message.author} ({user_id})")
                except Exception as e:
                    logging.error(f"Failed to delete message: {e}")
                    return

                # Notify the user in the warn channel
                warn_channel_id = await self._get_channel_id(SETTING_WARN_CHANNEL, DEFAULT_WARN_CHANNEL_ID)
                warn_channel = self.bot.get_channel(warn_channel_id)
                if warn_channel:
                    notification_text = (
                        f"We noticed you tried to post another introduction. "
                        f"You've already introduced yourself recently, so we removed your duplicate message.\n\n"
                        f"Feel free to chat with everyone in <#{GENERAL_CHANNEL_ID}> instead! "
                        f"We'd love to hear from you there. 😊"
                    )
                    await warn_channel.send(
                        content=f"Hey {message.author.mention}! 👋",
                        embed=yellow_embed(notification_text)
                    )
                    logging.info(f"Notified {message.author} about duplicate introduction")

                # Send staff alert with the message content and attempt count
                alert_channel_id = await self._get_channel_id(SETTING_ALERT_CHANNEL, DEFAULT_ALERT_CHANNEL_ID)
                alert_channel = self.bot.get_channel(alert_channel_id)
                if alert_channel:
                    alert_embed = Embed(
                        title="Duplicate Introduction Removed",
                        color=Color(int('e67e22', 16))
                    )
                    alert_embed.add_field(
                        name="User",
                        value=f"{message.author.mention} (`{user_id}`)",
                        inline=True
                    )
                    alert_embed.add_field(
                        name="Attempt",
                        value=f"This was their **{ordinal(attempt_count)}** introduction attempt",
                        inline=True
                    )
                    # Truncate long messages to fit in embed
                    display_content = saved_content[:1024] if len(saved_content) > 1024 else saved_content
                    alert_embed.add_field(
                        name="Message Content",
                        value=display_content,
                        inline=False
                    )
                    await alert_channel.send(embed=alert_embed)
                    logging.info(f"Sent staff alert about duplicate intro from {message.author} ({user_id})")

            else:
                # First introduction (within window) - record it
                await self.bot.db.record_introduction(user_id)
                logging.info(f"Recorded introduction from {message.author} ({user_id})")

        except Exception as e:
            logging.error(f"Error in introduction tracker: {e}")

    @command(aliases=['toggleintro'])
    @is_owner()
    async def introtracker(self, ctx, action: str = None, *, argument: str = None):
        """
        Toggle the introduction tracker on/off or configure channels
        Usage:
            !introtracker <on|off|status>
            !introtracker alertchannel <#channel>
            !introtracker warnchannel <#channel>
        """
        try:
            if action is None or action.lower() == 'status':
                is_enabled = await self.bot.db.get_feature_setting('intro_tracker')
                status = "enabled ✅" if is_enabled else "disabled ❌"
                await ctx.send(embed=green_embed(f"Introduction tracker is currently **{status}**"))
                return

            if action.lower() in ['on', 'enable', 'true', '1']:
                await self.bot.db.set_feature_setting('intro_tracker', True)
                await ctx.send(embed=green_embed("Introduction tracker **enabled** ✅"))
                logging.info(f"Introduction tracker enabled by {ctx.author}")

            elif action.lower() in ['off', 'disable', 'false', '0']:
                await self.bot.db.set_feature_setting('intro_tracker', False)
                await ctx.send(embed=red_embed("Introduction tracker **disabled** ❌"))
                logging.info(f"Introduction tracker disabled by {ctx.author}")

            elif action.lower() == 'alertchannel':
                if not ctx.message.channel_mentions:
                    await ctx.send(embed=red_embed("Usage: `!introtracker alertchannel <#channel>`"))
                    return
                channel = ctx.message.channel_mentions[0]
                await self.bot.db.set_bot_setting(SETTING_ALERT_CHANNEL, channel.id)
                await ctx.send(embed=green_embed(f"Staff alert channel set to {channel.mention} ✅"))
                logging.info(f"Intro alert channel set to {channel.id} by {ctx.author}")

            elif action.lower() == 'warnchannel':
                if not ctx.message.channel_mentions:
                    await ctx.send(embed=red_embed("Usage: `!introtracker warnchannel <#channel>`"))
                    return
                channel = ctx.message.channel_mentions[0]
                await self.bot.db.set_bot_setting(SETTING_WARN_CHANNEL, channel.id)
                await ctx.send(embed=green_embed(f"User warning channel set to {channel.mention} ✅"))
                logging.info(f"Intro warn channel set to {channel.id} by {ctx.author}")

            else:
                await ctx.send(embed=red_embed(
                    "Invalid action. Use:\n"
                    "`!introtracker <on|off|status>`\n"
                    "`!introtracker alertchannel <#channel>`\n"
                    "`!introtracker warnchannel <#channel>`"
                ))

        except Exception as e:
            logging.error(f"Error in introtracker command: {e}")
            await ctx.send(embed=red_embed(f"Error: {str(e)}"))

    @command(aliases=['introstats'])
    @is_owner()
    async def introstatus(self, ctx):
        """
        Show introduction tracker statistics
        Usage: !introstatus
        """
        try:
            is_enabled = await self.bot.db.get_feature_setting('intro_tracker')
            status = "Enabled ✅" if is_enabled else "Disabled ❌"

            warn_channel_id = await self._get_channel_id(SETTING_WARN_CHANNEL, DEFAULT_WARN_CHANNEL_ID)
            alert_channel_id = await self._get_channel_id(SETTING_ALERT_CHANNEL, DEFAULT_ALERT_CHANNEL_ID)

            # Get count of tracked introductions
            if self.bot.db.pool is None:
                raise RuntimeError("Database pool not initialized.")

            async with self.bot.db.pool.acquire() as conn:
                total_count = await conn.fetchval('SELECT COUNT(*) FROM introductions')
                unique_users = await conn.fetchval('SELECT COUNT(DISTINCT user_id) FROM introductions')
                recent_count = await conn.fetchval('''
                    SELECT COUNT(*) FROM introductions
                    WHERE posted_at > NOW() - INTERVAL '90 days'
                ''')

            embed = Embed(
                title="Introduction Tracker Status",
                color=Color(int('3498db', 16))
            )
            embed.add_field(name="Status", value=status, inline=False)
            embed.add_field(name="Watched Channel", value=f"<#{INTRO_CHANNEL_ID}>", inline=True)
            embed.add_field(name="Warn Channel", value=f"<#{warn_channel_id}>", inline=True)
            embed.add_field(name="Alert Channel", value=f"<#{alert_channel_id}>", inline=True)
            embed.add_field(name="Redirect Channel", value=f"<#{GENERAL_CHANNEL_ID}>", inline=True)
            embed.add_field(name="Total Introductions", value=str(total_count), inline=True)
            embed.add_field(name="Unique Users", value=str(unique_users), inline=True)
            embed.add_field(name="Recent (90d)", value=str(recent_count), inline=True)

            await ctx.send(embed=embed)

        except Exception as e:
            logging.error(f"Error showing intro stats: {e}")
            await ctx.send(embed=red_embed(f"Error: {str(e)}"))


async def setup(bot):
    await bot.add_cog(IntroductionTracker(bot))
