from discord.ext.commands import command, Bot, is_owner, Cog
from base_cog import BaseCog
from discord import Embed, Color, Message
import logging

# Channel IDs
INTRO_CHANNEL_ID = 399713966781235200  # Channel to watch for introductions
NOTIFY_CHANNEL_ID = 247135634265735168  # Channel to notify users about violations
GENERAL_CHANNEL_ID = 296491080881537024  # General chat channel to redirect users to

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


class IntroductionTracker(BaseCog):
    def __init__(self, bot: Bot):
        super().__init__(bot)

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

            # Check if user has already posted an introduction in the last 30 days
            existing_intro = await self.bot.db.check_user_introduction(user_id)

            if existing_intro:
                # User has already posted - delete the message
                try:
                    await message.delete()
                    logging.info(f"Deleted duplicate introduction from {message.author} ({user_id})")
                except Exception as e:
                    logging.error(f"Failed to delete message: {e}")
                    return

                # Notify the user in the redirect channel
                notify_channel = self.bot.get_channel(NOTIFY_CHANNEL_ID)
                if notify_channel:
                    # TODO: Make this message customizable with user_id parameter
                    notification_text = (
                        f"We noticed you tried to post another introduction. "
                        f"You've already introduced yourself recently, so we removed your duplicate message.\n\n"
                        f"Feel free to chat with everyone in <#{GENERAL_CHANNEL_ID}> instead! "
                        f"We'd love to hear from you there. 😊"
                    )
                    # Put mention in content (not embed) to trigger ping notification
                    await notify_channel.send(
                        content=f"Hey {message.author.mention}! 👋",
                        embed=yellow_embed(notification_text)
                    )
                    logging.info(f"Notified {message.author} about duplicate introduction")

            else:
                # First introduction - record it
                await self.bot.db.record_introduction(user_id)
                logging.info(f"Recorded introduction from {message.author} ({user_id})")

        except Exception as e:
            logging.error(f"Error in introduction tracker: {e}")

    @command(aliases=['toggleintro'])
    @is_owner()
    async def introtracker(self, ctx, action: str = None):
        """
        Toggle the introduction tracker on/off
        Usage: !introtracker <on|off|status>
        """
        try:
            if action is None or action.lower() == 'status':
                # Show current status
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

            else:
                await ctx.send(embed=red_embed(
                    "Invalid action. Use: `!introtracker <on|off|status>`"
                ))

        except Exception as e:
            logging.error(f"Error toggling intro tracker: {e}")
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

            # Get count of tracked introductions
            if self.bot.db.pool is None:
                raise RuntimeError("Database pool not initialized.")

            async with self.bot.db.pool.acquire() as conn:
                total_count = await conn.fetchval('SELECT COUNT(*) FROM introductions')
                recent_count = await conn.fetchval('''
                    SELECT COUNT(*) FROM introductions
                    WHERE posted_at > NOW() - INTERVAL '30 days'
                ''')

            embed = Embed(
                title="Introduction Tracker Status",
                color=Color(int('3498db', 16))
            )
            embed.add_field(name="Status", value=status, inline=False)
            embed.add_field(name="Watched Channel", value=f"<#{INTRO_CHANNEL_ID}>", inline=True)
            embed.add_field(name="Notify Channel", value=f"<#{NOTIFY_CHANNEL_ID}>", inline=True)
            embed.add_field(name="Redirect Channel", value=f"<#{GENERAL_CHANNEL_ID}>", inline=True)
            embed.add_field(name="Total Introductions", value=str(total_count), inline=True)
            embed.add_field(name="Recent (30d)", value=str(recent_count), inline=True)

            await ctx.send(embed=embed)

        except Exception as e:
            logging.error(f"Error showing intro stats: {e}")
            await ctx.send(embed=red_embed(f"Error: {str(e)}"))


async def setup(bot):
    await bot.add_cog(IntroductionTracker(bot))
