"""
Language League Cog
Tracks user activity and maintains league rankings for language learners
"""
import discord
from discord.ext import commands
from discord import app_commands, Interaction, Embed, Member
from base_cog import BaseCog
import logging
import time
from typing import Optional
from langdetect import detect, DetectorFactory, LangDetectException

# Set seed for consistent language detection results
DetectorFactory.seed = 0

logger = logging.getLogger(__name__)

# Guild ID - Language League is only available in this server
LEAGUE_GUILD_ID = 243838819743432704

# Role IDs
ENGLISH_NATIVE = 243853718758359040
SPANISH_NATIVE = 243854128424550401
LEARNING_SPANISH = 297415063302832128
LEARNING_ENGLISH = 247021017740869632
OTHER_NATIVE = 247020385730691073


class LeagueCog(BaseCog):
    """Cog for managing the opt-in Language League"""

    def __init__(self, bot: commands.Bot):
        super().__init__(bot)
        # In-memory cooldown cache: {user_id: {channel_id: timestamp}}
        self.message_cooldowns = {}

    league_group = app_commands.Group(
        name="league",
        description="Language League - Compete with other learners!",
        guild_ids=[LEAGUE_GUILD_ID]  # Guild-specific for instant sync
    )

    async def validate_user_roles(self, member: Member) -> dict:
        """
        Validate user roles for Language League opt-in.

        Returns:
            {
                'valid': bool,
                'learning_spanish': bool,
                'learning_english': bool,
                'error_message': str or None
            }
        """
        # Get user's role IDs
        user_role_ids = [role.id for role in member.roles]

        # Check what roles they have
        has_english_native = ENGLISH_NATIVE in user_role_ids
        has_spanish_native = SPANISH_NATIVE in user_role_ids
        has_learning_spanish = LEARNING_SPANISH in user_role_ids
        has_learning_english = LEARNING_ENGLISH in user_role_ids

        # Rule 1: Must have EXACTLY ONE Learning role
        if not has_learning_spanish and not has_learning_english:
            return {
                'valid': False,
                'learning_spanish': False,
                'learning_english': False,
                'error_message': (
                    "❌ **Invalid Role Configuration**\n\n"
                    "You must have exactly one learning role:\n"
                    f"• <@&{LEARNING_SPANISH}> (Learning Spanish)\n"
                    f"• <@&{LEARNING_ENGLISH}> (Learning English)\n\n"
                    "Please add the appropriate role and try again!"
                )
            }

        # Rule 2: Cannot have BOTH learning roles
        if has_learning_spanish and has_learning_english:
            return {
                'valid': False,
                'learning_spanish': False,
                'learning_english': False,
                'error_message': (
                    "❌ **Too Many Learning Roles**\n\n"
                    "You can only participate in ONE league at a time.\n"
                    "You currently have both:\n"
                    f"• <@&{LEARNING_SPANISH}> (Learning Spanish)\n"
                    f"• <@&{LEARNING_ENGLISH}> (Learning English)\n\n"
                    "Please keep only the role for the language you want to focus on!"
                )
            }

        # Rule 3: Cannot be native in language you're learning
        if has_learning_spanish and has_spanish_native:
            return {
                'valid': False,
                'learning_spanish': False,
                'learning_english': False,
                'error_message': (
                    "❌ **Conflicting Roles**\n\n"
                    "You have both:\n"
                    f"• <@&{LEARNING_SPANISH}> (Learning Spanish)\n"
                    f"• <@&{SPANISH_NATIVE}> (Spanish Native)\n\n"
                    "You cannot be native in a language you're learning.\n"
                    "Please remove one of these roles and try again!"
                )
            }

        if has_learning_english and has_english_native:
            return {
                'valid': False,
                'learning_spanish': False,
                'learning_english': False,
                'error_message': (
                    "❌ **Conflicting Roles**\n\n"
                    "You have both:\n"
                    f"• <@&{LEARNING_ENGLISH}> (Learning English)\n"
                    f"• <@&{ENGLISH_NATIVE}> (English Native)\n\n"
                    "You cannot be native in a language you're learning.\n"
                    "Please remove one of these roles and try again!"
                )
            }

        # All checks passed
        return {
            'valid': True,
            'learning_spanish': has_learning_spanish,
            'learning_english': has_learning_english,
            'error_message': None
        }

    @league_group.command(name="join", description="Join the Language League")
    async def league_join(self, interaction: Interaction):
        """Join the Language League (opt-in)"""
        try:
            # Validate roles
            validation = await self.validate_user_roles(interaction.user)

            if not validation['valid']:
                embed = Embed(
                    description=validation['error_message'],
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            # Join league
            await self.bot.db.leaderboard_join(
                user_id=interaction.user.id,
                username=str(interaction.user),
                learning_spanish=validation['learning_spanish'],
                learning_english=validation['learning_english']
            )

            # Build success message
            league_name = "Spanish League 🇪🇸" if validation['learning_spanish'] else "English League 🇬🇧"
            language_name = "Spanish" if validation['learning_spanish'] else "English"

            embed = Embed(
                title="✅ Welcome to the Language League!",
                description=(
                    f"You're now competing in the **{league_name}**!\n\n"
                    f"📝 **How it works:**\n"
                    f"• Only messages in **{language_name}** will count\n"
                    f"• Messages must be at least 10 characters\n"
                    f"• 2-minute cooldown per channel (no spam!)\n"
                    f"• Max 50 counted messages per day\n"
                    f"• +5 bonus points for each active day\n\n"
                    f"Use `/league stats` to track your progress!\n\n"
                    f"Good luck! 🎯"
                ),
                color=discord.Color.green()
            )

            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.info(f"User {interaction.user} ({interaction.user.id}) joined Language League")

        except Exception as e:
            logger.error(f"Error in league join: {e}", exc_info=True)
            embed = Embed(
                title="❌ Error",
                description=f"Failed to join Language League: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @league_group.command(name="leave", description="Leave the Language League")
    async def league_leave(self, interaction: Interaction):
        """Leave the Language League (opt-out)"""
        try:
            success = await self.bot.db.leaderboard_leave(interaction.user.id)

            if success:
                embed = Embed(
                    title="👋 Left the Language League",
                    description=(
                        "You've been removed from league rankings.\n\n"
                        "Your historical data is preserved, but you won't appear on the leagues.\n"
                        "Use `/league join` if you want to rejoin!"
                    ),
                    color=discord.Color.blue()
                )
            else:
                embed = Embed(
                    title="ℹ️ Not Found",
                    description="You weren't in the Language League.",
                    color=discord.Color.orange()
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.info(f"User {interaction.user} ({interaction.user.id}) left Language League")

        except Exception as e:
            logger.error(f"Error in league leave: {e}", exc_info=True)
            embed = Embed(
                title="❌ Error",
                description=f"Failed to leave Language League: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @league_group.command(name="view", description="View league rankings")
    @app_commands.describe(
        board="Which league to view",
        limit="Number of users to show (max 25)"
    )
    @app_commands.choices(board=[
        app_commands.Choice(name="Spanish League 🇪🇸", value="spanish"),
        app_commands.Choice(name="English League 🇬🇧", value="english"),
        app_commands.Choice(name="Combined League 🌍", value="combined")
    ])
    async def league_view(
        self,
        interaction: Interaction,
        board: str = "combined",
        limit: int = 10
    ):
        """View league rankings"""
        try:
            # Validate limit
            if limit < 1 or limit > 25:
                embed = Embed(
                    title="❌ Invalid Limit",
                    description="Limit must be between 1 and 25.",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            # Get league data
            rankings = await self.bot.db.get_leaderboard(board, limit)

            if not rankings:
                embed = Embed(
                    title=f"📊 {board.title()} League",
                    description="No users in this league yet!\n\nUse `/league join` to be the first!",
                    color=discord.Color.blue()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            # Build league embed
            board_emoji = "🇪🇸" if board == "spanish" else ("🇬🇧" if board == "english" else "🌍")
            embed = Embed(
                title=f"{board_emoji} {board.title()} League (Last 30 Days)",
                color=discord.Color.gold()
            )

            # Format rankings
            description_lines = []
            description_lines.append("```")
            description_lines.append(f"{'Rank':<6}{'User':<20}{'Score':<8}{'Days':<6}")
            description_lines.append("-" * 45)

            for entry in rankings:
                rank = entry['rank']
                username = entry['username'][:17] + "..." if len(entry['username']) > 20 else entry['username']
                score = entry['total_score']
                days = entry['active_days']

                # Add medal emojis for top 3
                rank_display = f"#{rank}"
                if rank == 1:
                    rank_display = "🥇"
                elif rank == 2:
                    rank_display = "🥈"
                elif rank == 3:
                    rank_display = "🥉"

                description_lines.append(f"{rank_display:<6}{username:<20}{score:<8}{days:<6}")

            description_lines.append("```")
            embed.description = "\n".join(description_lines)

            embed.add_field(
                name="ℹ️ Scoring",
                value="Score = Points + (Active Days × 5)",
                inline=False
            )

            embed.set_footer(text=f"Use /league stats to see your ranking")

            await interaction.response.send_message(embed=embed)
            logger.info(f"User {interaction.user} viewed {board} league")

        except Exception as e:
            logger.error(f"Error viewing league: {e}", exc_info=True)
            embed = Embed(
                title="❌ Error",
                description=f"Failed to load league: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @league_group.command(name="stats", description="View league stats")
    @app_commands.describe(
        user="User to view stats for (leave empty for yourself)"
    )
    async def league_stats(
        self,
        interaction: Interaction,
        user: Optional[Member] = None
    ):
        """View personal or another user's stats"""
        try:
            target = user or interaction.user

            # Get stats
            stats = await self.bot.db.get_user_stats(target.id)

            if not stats:
                embed = Embed(
                    title="ℹ️ Not Found",
                    description=(
                        f"{'You are' if target == interaction.user else f'{target.display_name} is'} not in the league system.\n\n"
                        f"Use `/league join` to {'join' if target == interaction.user else 'get them to join'}!"
                    ),
                    color=discord.Color.orange()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            # Build stats embed
            is_self = target == interaction.user
            title = "📊 Your League Stats" if is_self else f"📊 {target.display_name}'s League Stats"

            embed = Embed(
                title=title,
                description=f"**Last 30 Days**",
                color=discord.Color.blue()
            )

            embed.add_field(
                name="Points & Activity",
                value=(
                    f"**Total Points:** {stats['total_points']}\n"
                    f"**Active Days:** {stats['active_days']}\n"
                    f"**Total Score:** {stats['total_score']} ({stats['total_points']} + {stats['active_days'] * 5} bonus)"
                ),
                inline=False
            )

            # Rankings
            rankings_text = []
            if stats['rank_spanish']:
                rankings_text.append(f"🇪🇸 Spanish: **#{stats['rank_spanish']}**")
            if stats['rank_english']:
                rankings_text.append(f"🇬🇧 English: **#{stats['rank_english']}**")
            if stats['rank_combined']:
                rankings_text.append(f"🌍 Combined: **#{stats['rank_combined']}**")

            if rankings_text:
                embed.add_field(
                    name="Rankings",
                    value="\n".join(rankings_text),
                    inline=False
                )

            if is_self and stats['active_days'] > 0:
                embed.set_footer(text="Keep it up! Try to stay active daily for consistency bonuses! 🔥")

            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.info(f"User {interaction.user} viewed stats for {target}")

        except Exception as e:
            logger.error(f"Error viewing stats: {e}", exc_info=True)
            embed = Embed(
                title="❌ Error",
                description=f"Failed to load stats: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    # Admin Commands (Prefix)

    @commands.command(name="league")
    @commands.is_owner()
    async def league_admin(self, ctx, action: str = None, target=None):
        """Admin league management (Owner only)"""
        if not action:
            await ctx.send("❌ Usage: `$league <ban|unban|exclude|include|excluded|admin_stats> [target]`")
            return

        action = action.lower()

        if action == "ban":
            if not target:
                await ctx.send("❌ Usage: `$league ban <user_id|@user>`")
                return

            # Get user ID
            try:
                if ctx.message.mentions:
                    user_id = ctx.message.mentions[0].id
                else:
                    user_id = int(target)

                success = await self.bot.db.leaderboard_ban_user(user_id)
                if success:
                    await ctx.send(f"✅ Banned user `{user_id}` from league.")
                    logger.info(f"Admin {ctx.author} banned user {user_id} from league")
                else:
                    await ctx.send(f"❌ Failed to ban user `{user_id}`.")
            except ValueError:
                await ctx.send("❌ Invalid user ID.")

        elif action == "unban":
            if not target:
                await ctx.send("❌ Usage: `$league unban <user_id|@user>`")
                return

            try:
                if ctx.message.mentions:
                    user_id = ctx.message.mentions[0].id
                else:
                    user_id = int(target)

                success = await self.bot.db.leaderboard_unban_user(user_id)
                if success:
                    await ctx.send(f"✅ Unbanned user `{user_id}` from league.")
                    logger.info(f"Admin {ctx.author} unbanned user {user_id} from league")
                else:
                    await ctx.send(f"❌ Failed to unban user `{user_id}`.")
            except ValueError:
                await ctx.send("❌ Invalid user ID.")

        elif action == "exclude":
            if not ctx.message.channel_mentions:
                await ctx.send("❌ Usage: `$league exclude <#channel>`")
                return

            channel = ctx.message.channel_mentions[0]
            success = await self.bot.db.exclude_channel(channel.id, channel.name, ctx.author.id)
            if success:
                await ctx.send(f"✅ Excluded {channel.mention} from league tracking.")
                logger.info(f"Admin {ctx.author} excluded channel {channel.name} ({channel.id}) from league")
            else:
                await ctx.send(f"❌ Failed to exclude {channel.mention}.")

        elif action == "include":
            if not ctx.message.channel_mentions:
                await ctx.send("❌ Usage: `$league include <#channel>`")
                return

            channel = ctx.message.channel_mentions[0]
            success = await self.bot.db.include_channel(channel.id)
            if success:
                await ctx.send(f"✅ Re-included {channel.mention} in league tracking.")
                logger.info(f"Admin {ctx.author} re-included channel {channel.name} ({channel.id}) in league")
            else:
                await ctx.send(f"❌ Channel {channel.mention} was not excluded.")

        elif action == "excluded":
            channels = await self.bot.db.get_excluded_channels()
            if not channels:
                await ctx.send("ℹ️ No channels are currently excluded.")
                return

            embed = Embed(
                title="🚫 Excluded Channels",
                description=f"Total: {len(channels)} channels",
                color=discord.Color.blue()
            )

            channel_list = []
            for ch in channels[:25]:  # Limit to 25
                channel_list.append(f"<#{ch['channel_id']}> (`{ch['channel_id']}`)")

            embed.add_field(
                name="Channels",
                value="\n".join(channel_list) if channel_list else "None",
                inline=False
            )

            await ctx.send(embed=embed)

        elif action == "admin_stats":
            # Get system stats (would need new DB method)
            await ctx.send("📊 Admin stats coming soon!")

        else:
            await ctx.send(f"❌ Unknown action: `{action}`")

    # Message Listener for Activity Tracking

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Track messages for league"""
        try:
            # Ignore bots
            if message.author.bot:
                return

            # Ignore DMs
            if not message.guild:
                return

            # Only track activity in the league guild
            if message.guild.id != LEAGUE_GUILD_ID:
                return

            # Check if user is opted in
            if not await self.bot.db.is_user_opted_in(message.author.id):
                return

            # Check if user is banned
            if await self.bot.db.is_user_banned(message.author.id):
                return

            # Check if channel is excluded
            if await self.bot.db.is_channel_excluded(message.channel.id):
                return

            # Anti-spam: Check message cooldown
            if not self.check_message_cooldown(message.author.id, message.channel.id):
                return  # Too soon, don't count

            # Anti-spam: Check daily cap
            daily_count = await self.bot.db.get_daily_message_count(message.author.id)
            if daily_count >= 50:
                return  # Hit daily cap

            # Language detection: Only count messages in the language being learned
            detected_lang = self.detect_message_language(message.content)
            if not detected_lang:
                return  # Could not detect language or message too short

            # Get what language(s) the user is learning
            learning = await self.bot.db.get_user_learning_languages(message.author.id)

            # Check if message is in the language they're learning
            is_valid_message = False
            if detected_lang == 'es' and learning['learning_spanish']:
                is_valid_message = True
            elif detected_lang == 'en' and learning['learning_english']:
                is_valid_message = True

            if not is_valid_message:
                return  # Message not in the language they're learning

            # Record activity
            await self.bot.db.record_activity(
                user_id=message.author.id,
                activity_type='message',
                channel_id=message.channel.id,
                points=1
            )

            # Update cooldown cache
            self.update_message_cooldown(message.author.id, message.channel.id)

        except Exception as e:
            logger.error(f"Error in league message tracking: {e}", exc_info=True)

    def check_message_cooldown(self, user_id: int, channel_id: int) -> bool:
        """Check if enough time has passed since last counted message"""
        now = time.time()
        cooldown_seconds = 120  # 2 minutes

        if user_id not in self.message_cooldowns:
            return True

        if channel_id not in self.message_cooldowns[user_id]:
            return True

        last_time = self.message_cooldowns[user_id][channel_id]
        return (now - last_time) >= cooldown_seconds

    def update_message_cooldown(self, user_id: int, channel_id: int):
        """Update the last message time for cooldown tracking"""
        if user_id not in self.message_cooldowns:
            self.message_cooldowns[user_id] = {}

        self.message_cooldowns[user_id][channel_id] = time.time()

    def detect_message_language(self, message_content: str) -> Optional[str]:
        """
        Detect the language of a message using langdetect.

        Returns:
            'es' for Spanish, 'en' for English, None if uncertain or error
        """
        # Skip very short messages (hard to detect accurately)
        if len(message_content.strip()) < 10:
            return None

        try:
            detected_lang = detect(message_content)

            # Only return if we detected Spanish or English
            if detected_lang in ['es', 'en']:
                return detected_lang

            return None
        except LangDetectException:
            # Detection failed (empty string, etc.)
            return None
        except Exception as e:
            logger.error(f"Language detection error: {e}")
            return None


async def setup(bot):
    """Setup function to add the cog to the bot"""
    await bot.add_cog(LeagueCog(bot))
    logger.info("LeagueCog loaded successfully")
