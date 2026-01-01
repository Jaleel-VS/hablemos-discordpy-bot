"""
Language League Cog
Tracks user activity and maintains league rankings for language learners
"""
import discord
from discord.ext import commands, tasks
from discord import app_commands, Interaction, Embed, Member, File
from base_cog import BaseCog
import logging
import time
from typing import Optional
from langdetect import detect, DetectorFactory, LangDetectException
from datetime import datetime, timedelta, timezone
from cogs.league_cog.config import (
    LEAGUE_GUILD_ID,
    WINNER_CHANNEL_ID,
    ROLES,
    SCORING,
    RATE_LIMITS,
    ROUNDS,
    DISPLAY,
    LANGUAGE
)

# Set seed for consistent language detection results
DetectorFactory.seed = LANGUAGE.LANGDETECT_SEED

logger = logging.getLogger(__name__)


class LeagueCog(BaseCog):
    """Cog for managing the opt-in Language League"""

    def __init__(self, bot: commands.Bot):
        super().__init__(bot)
        # In-memory cooldown cache: {user_id: {channel_id: timestamp}}
        self.message_cooldowns = {}
        self.check_round_end.start()  # Start scheduled task

    async def cog_load(self):
        """Called when cog is loaded - ensure we have an active round"""
        await self.ensure_round_exists()

    def cog_unload(self):
        """Called when cog is unloaded"""
        self.check_round_end.cancel()

    async def ensure_round_exists(self):
        """Create initial round if none exists"""
        try:
            current_round = await self.bot.db.get_current_round()
            if not current_round:
                # Start today, end next Sunday midnight UTC
                start_date = datetime.now(timezone.utc)
                # Calculate next Sunday
                days_until_sunday = (6 - start_date.weekday()) % 7
                if days_until_sunday == 0:
                    days_until_sunday = 7
                end_date = start_date + timedelta(days=days_until_sunday)
                end_date = end_date.replace(hour=23, minute=59, second=59)

                round_id = await self.bot.db.create_round(1, start_date, end_date)
                logger.info(f"Created initial round {round_id}: {start_date} to {end_date}")
        except Exception as e:
            logger.error(f"Error ensuring round exists: {e}", exc_info=True)

    @tasks.loop(minutes=ROUNDS.ROUND_CHECK_INTERVAL_MINUTES)
    async def check_round_end(self):
        """Scheduled task to check if current round has ended"""
        try:
            current_round = await self.bot.db.get_current_round()
            if not current_round:
                return

            now = datetime.now(timezone.utc)
            end_date = current_round['end_date']

            # Make end_date timezone-aware if it isn't
            if end_date.tzinfo is None:
                end_date = end_date.replace(tzinfo=timezone.utc)

            # Check if round has ended
            if now >= end_date:
                logger.info(f"Round {current_round['round_id']} has ended, processing...")
                await self.end_current_round(current_round)

        except Exception as e:
            logger.error(f"Error in check_round_end task: {e}", exc_info=True)

    @check_round_end.before_loop
    async def before_check_round_end(self):
        """Wait for bot to be ready before starting the round check task"""
        await self.bot.wait_until_ready()

    async def end_current_round(self, current_round: dict):
        """
        End the current round and announce winners

        Args:
            current_round: Dict with round info from get_current_round()
        """
        try:
            round_id = current_round['round_id']
            round_number = current_round['round_number']

            logger.info(f"Ending round {round_number} (ID: {round_id})")

            # Get top 3 from Spanish league
            spanish_top3 = await self.bot.db.get_leaderboard('spanish', limit=SCORING.TOP_WINNERS_COUNT, round_id=round_id)

            # Get top 3 from English league
            english_top3 = await self.bot.db.get_leaderboard('english', limit=SCORING.TOP_WINNERS_COUNT, round_id=round_id)

            # Save winners to database
            winners_data = []

            for rank, entry in enumerate(spanish_top3, start=1):
                winners_data.append({
                    'user_id': entry['user_id'],
                    'username': entry['username'],
                    'league_type': 'spanish',
                    'rank': rank,
                    'total_score': entry['total_score'],
                    'active_days': entry['active_days']
                })

            for rank, entry in enumerate(english_top3, start=1):
                winners_data.append({
                    'user_id': entry['user_id'],
                    'username': entry['username'],
                    'league_type': 'english',
                    'rank': rank,
                    'total_score': entry['total_score'],
                    'active_days': entry['active_days']
                })

            # Save all winners
            await self.bot.db.save_round_winners(round_id, winners_data)

            # Mark round as completed
            await self.bot.db.end_round(round_id)

            # Announce winners
            await self.announce_winners(round_number, spanish_top3, english_top3)

            # Create next round
            next_start = current_round['end_date'] + timedelta(seconds=1)
            next_end = next_start + timedelta(days=ROUNDS.ROUND_DURATION_DAYS)
            next_end = next_end.replace(hour=23, minute=59, second=59)

            next_round_id = await self.bot.db.create_round(round_number + 1, next_start, next_end)
            logger.info(f"Created next round {round_number + 1} (ID: {next_round_id}): {next_start} to {next_end}")

        except Exception as e:
            logger.error(f"Error ending round: {e}", exc_info=True)

    async def announce_winners(self, round_number: int, spanish_top3: list, english_top3: list):
        """
        Announce round winners in the winner announcement channel

        Args:
            round_number: The round number that just ended
            spanish_top3: List of top 3 Spanish league entries
            english_top3: List of top 3 English league entries
        """
        try:
            channel = self.bot.get_channel(WINNER_CHANNEL_ID)
            if not channel:
                logger.error(f"Could not find winner announcement channel {WINNER_CHANNEL_ID}")
                return

            embed = Embed(
                title=f"🏆 Round {round_number} Winners!",
                description="Congratulations to our top performers this round!",
                color=discord.Color.gold()
            )

            # Spanish League Winners
            if spanish_top3:
                spanish_text = []
                medals = ["🥇", "🥈", "🥉"]
                for i, entry in enumerate(spanish_top3):
                    user_mention = f"<@{entry['user_id']}>"
                    spanish_text.append(
                        f"{medals[i]} **{entry['username']}** {user_mention}\n"
                        f"   Score: {entry['total_score']} ({entry['active_days']} days)"
                    )

                embed.add_field(
                    name="🇪🇸 Spanish League",
                    value="\n\n".join(spanish_text),
                    inline=False
                )

            # English League Winners
            if english_top3:
                english_text = []
                medals = ["🥇", "🥈", "🥉"]
                for i, entry in enumerate(english_top3):
                    user_mention = f"<@{entry['user_id']}>"
                    english_text.append(
                        f"{medals[i]} **{entry['username']}** {user_mention}\n"
                        f"   Score: {entry['total_score']} ({entry['active_days']} days)"
                    )

                embed.add_field(
                    name="🇬🇧 English League",
                    value="\n\n".join(english_text),
                    inline=False
                )

            embed.set_footer(text=f"Round {round_number} • Keep learning and see you next round!")

            # Send announcement
            await channel.send(embed=embed)
            logger.info(f"Announced round {round_number} winners in channel {WINNER_CHANNEL_ID}")

        except Exception as e:
            logger.error(f"Error announcing winners: {e}", exc_info=True)

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
        has_english_native = ROLES.ENGLISH_NATIVE in user_role_ids
        has_spanish_native = ROLES.SPANISH_NATIVE in user_role_ids
        has_learning_spanish = ROLES.LEARNING_SPANISH in user_role_ids
        has_learning_english = ROLES.LEARNING_ENGLISH in user_role_ids

        # Rule 1: Must have EXACTLY ONE Learning role
        if not has_learning_spanish and not has_learning_english:
            return {
                'valid': False,
                'learning_spanish': False,
                'learning_english': False,
                'error_message': (
                    "❌ **Invalid Role Configuration**\n\n"
                    "You must have exactly one learning role:\n"
                    f"• <@&{ROLES.LEARNING_SPANISH}> (Learning Spanish)\n"
                    f"• <@&{ROLES.LEARNING_ENGLISH}> (Learning English)\n\n"
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
                    f"• <@&{ROLES.LEARNING_SPANISH}> (Learning Spanish)\n"
                    f"• <@&{ROLES.LEARNING_ENGLISH}> (Learning English)\n\n"
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
                    f"• <@&{ROLES.LEARNING_SPANISH}> (Learning Spanish)\n"
                    f"• <@&{ROLES.SPANISH_NATIVE}> (Spanish Native)\n\n"
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
                    f"• <@&{ROLES.LEARNING_ENGLISH}> (Learning English)\n"
                    f"• <@&{ROLES.ENGLISH_NATIVE}> (English Native)\n\n"
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
                    f"• Messages must be at least {RATE_LIMITS.MIN_MESSAGE_LENGTH} characters\n"
                    f"• {RATE_LIMITS.MESSAGE_COOLDOWN_SECONDS // 60}-minute cooldown per channel (no spam!)\n"
                    f"• Max {RATE_LIMITS.DAILY_MESSAGE_CAP} counted messages per day\n"
                    f"• +{SCORING.ACTIVE_DAY_BONUS_MULTIPLIER} bonus points for each active day\n\n"
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
    @app_commands.describe(board="Which league to view")
    @app_commands.choices(board=[
        app_commands.Choice(name="Spanish League 🇪🇸", value="spanish"),
        app_commands.Choice(name="English League 🇬🇧", value="english"),
        app_commands.Choice(name="Combined League 🌍", value="combined")
    ])
    async def league_view(
        self,
        interaction: Interaction,
        board: str = "combined"
    ):
        """View league rankings (top 20)"""
        try:
            # Get current round info
            current_round = await self.bot.db.get_current_round()
            if not current_round:
                embed = Embed(
                    title="ℹ️ No Active Round",
                    description="There is no active league round at the moment.",
                    color=discord.Color.orange()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            # Get top entries for image
            rankings = await self.bot.db.get_leaderboard(board, SCORING.LEADERBOARD_DISPLAY_LIMIT)

            if not rankings:
                embed = Embed(
                    title=f"📊 {board.title()} League",
                    description="No users in this league yet!\n\nUse `/league join` to be the first!",
                    color=discord.Color.blue()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            # Helper function for rank medals
            def get_rank_emoji(rank: int) -> str:
                medals = {1: "🥇", 2: "🥈", 3: "🥉"}
                return medals.get(rank, f"**#{rank}**")

            # Check if requester is in top rankings
            requester_in_top = any(entry['user_id'] == interaction.user.id for entry in rankings)
            requester_stats = None

            # If not in top rankings, get their stats for the embed
            if not requester_in_top:
                user_stats = await self.bot.db.get_user_stats(interaction.user.id)
                if user_stats:
                    # Determine which rank to show based on board type
                    if board == 'spanish' and user_stats.get('rank_spanish'):
                        requester_stats = {
                            'rank': user_stats['rank_spanish'],
                            'username': str(interaction.user),
                            'total_score': user_stats['total_score'],
                            'active_days': user_stats['active_days'],
                            'user_id': interaction.user.id
                        }
                    elif board == 'english' and user_stats.get('rank_english'):
                        requester_stats = {
                            'rank': user_stats['rank_english'],
                            'username': str(interaction.user),
                            'total_score': user_stats['total_score'],
                            'active_days': user_stats['active_days'],
                            'user_id': interaction.user.id
                        }
                    elif board == 'combined' and user_stats.get('rank_combined'):
                        requester_stats = {
                            'rank': user_stats['rank_combined'],
                            'username': str(interaction.user),
                            'total_score': user_stats['total_score'],
                            'active_days': user_stats['active_days'],
                            'user_id': interaction.user.id
                        }

            # Create embed leaderboard
            board_emoji = DISPLAY.get_emoji(board)
            board_title = DISPLAY.get_name(board)

            embed = Embed(
                title=f"{board_emoji} {board_title}",
                description=f"**Round {current_round['round_number']}**",
                color=discord.Color.gold()
            )

            # Build leaderboard entries
            leaderboard_lines = []
            for entry in rankings:
                rank_display = get_rank_emoji(entry['rank'])

                # Check if previous winner
                is_winner = await self.bot.db.has_user_won_before(entry['user_id'])
                star = "⭐ " if is_winner else ""

                # Format entry line
                line = f"{rank_display} {star}**{entry['username']}**\n     {entry['total_score']} pts • {entry['active_days']} days active"
                leaderboard_lines.append(line)

            # Add leaderboard to embed (split into chunks if needed to avoid field limit)
            chunk_size = 10
            for i in range(0, len(leaderboard_lines), chunk_size):
                chunk = leaderboard_lines[i:i + chunk_size]
                field_name = "📊 Rankings" if i == 0 else "\u200b"  # Zero-width space for continuation
                embed.add_field(
                    name=field_name,
                    value="\n\n".join(chunk),
                    inline=False
                )

            # Add requester's rank if outside top rankings
            if requester_stats and requester_stats['rank'] > SCORING.LEADERBOARD_DISPLAY_LIMIT:
                has_won = await self.bot.db.has_user_won_before(requester_stats['user_id'])
                star = "⭐ " if has_won else ""
                embed.add_field(
                    name="📍 Your Rank",
                    value=f"{star}**#{requester_stats['rank']}** • {requester_stats['total_score']} pts • {requester_stats['active_days']} active days",
                    inline=False
                )

            # Add scoring info
            embed.add_field(
                name="ℹ️ How Scoring Works",
                value=f"Score = Points + (Active Days × {SCORING.ACTIVE_DAY_BONUS_MULTIPLIER})\n⭐ = Previous #1 winner",
                inline=False
            )

            # Show round end date in footer
            end_date = current_round['end_date']
            if end_date.tzinfo is None:
                end_date = end_date.replace(tzinfo=timezone.utc)

            embed.set_footer(text=f"Ends: {end_date.strftime('%Y-%m-%d %H:%M')} UTC")

            # Send embed
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

            # Get current round info
            current_round = await self.bot.db.get_current_round()
            if not current_round:
                embed = Embed(
                    title="ℹ️ No Active Round",
                    description="There is no active league round at the moment.",
                    color=discord.Color.orange()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

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

            # Check if user has won before
            has_won = await self.bot.db.has_user_won_before(target.id)
            star = " ⭐" if has_won else ""

            embed = Embed(
                title=title + star,
                description=f"**Round {current_round['round_number']}**",
                color=discord.Color.blue()
            )

            embed.add_field(
                name="Points & Activity",
                value=(
                    f"**Total Points:** {stats['total_points']}\n"
                    f"**Active Days:** {stats['active_days']}\n"
                    f"**Total Score:** {stats['total_score']} ({stats['total_points']} + {stats['active_days'] * SCORING.ACTIVE_DAY_BONUS_MULTIPLIER} bonus)"
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

            # Show round end date in footer
            end_date = current_round['end_date']
            if end_date.tzinfo is None:
                end_date = end_date.replace(tzinfo=timezone.utc)

            footer_text = f"Round ends: {end_date.strftime('%Y-%m-%d %H:%M')} UTC"
            if is_self and stats['active_days'] > 0:
                footer_text += " • Keep it up! 🔥"

            embed.set_footer(text=footer_text)

            await interaction.response.send_message(embed=embed)
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
            # Get league statistics
            stats = await self.bot.db.get_league_admin_stats()

            embed = Embed(
                title="📊 Language League - Admin Statistics",
                color=discord.Color.blue()
            )

            embed.add_field(
                name="👥 Participant Breakdown",
                value=(
                    f"**Total Active Users:** {stats['total_users']}\n"
                    f"🇪🇸 Spanish Learners: {stats['spanish_learners']}\n"
                    f"🇬🇧 English Learners: {stats['english_learners']}\n"
                    f"🚫 Banned Users: {stats['banned_users']}"
                ),
                inline=False
            )

            embed.add_field(
                name="📈 Activity (Last 30 Days)",
                value=f"**Total Messages Counted:** {stats['total_messages_30d']:,}",
                inline=False
            )

            # Get excluded channels count
            excluded_channels = await self.bot.db.get_excluded_channels()
            embed.add_field(
                name="⚙️ Configuration",
                value=f"**Excluded Channels:** {len(excluded_channels)}",
                inline=False
            )

            await ctx.send(embed=embed)
            logger.info(f"Admin {ctx.author} viewed league statistics")

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
            if daily_count >= RATE_LIMITS.DAILY_MESSAGE_CAP:
                return  # Hit daily cap

            # Language detection: Only count messages in the language being learned
            detected_lang = self.detect_message_language(message.content)
            if not detected_lang:
                return  # Could not detect language or message too short

            # Get what language(s) the user is learning
            learning = await self.bot.db.get_user_learning_languages(message.author.id)

            # Check if message is in the language they're learning
            is_valid_message = False
            if detected_lang == LANGUAGE.SPANISH_CODE and learning['learning_spanish']:
                is_valid_message = True
            elif detected_lang == LANGUAGE.ENGLISH_CODE and learning['learning_english']:
                is_valid_message = True

            if not is_valid_message:
                return  # Message not in the language they're learning

            # Get current round
            current_round = await self.bot.db.get_current_round()
            if not current_round:
                logger.warning("No active round found, cannot record activity")
                return

            # Record activity
            await self.bot.db.record_activity(
                user_id=message.author.id,
                activity_type='message',
                channel_id=message.channel.id,
                points=SCORING.POINTS_PER_MESSAGE,
                round_id=current_round['round_id']
            )

            # Update cooldown cache
            self.update_message_cooldown(message.author.id, message.channel.id)

        except Exception as e:
            logger.error(f"Error in league message tracking: {e}", exc_info=True)

    def check_message_cooldown(self, user_id: int, channel_id: int) -> bool:
        """Check if enough time has passed since last counted message"""
        now = time.time()
        cooldown_seconds = RATE_LIMITS.MESSAGE_COOLDOWN_SECONDS

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
        if len(message_content.strip()) < RATE_LIMITS.MIN_MESSAGE_LENGTH:
            return None

        try:
            detected_lang = detect(message_content)

            # Only return if we detected Spanish or English
            if detected_lang in [LANGUAGE.SPANISH_CODE, LANGUAGE.ENGLISH_CODE]:
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
