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
import functools
from typing import Optional, Callable, TypeVar, ParamSpec
from pathlib import Path
from langdetect import DetectorFactory
from datetime import datetime, timedelta, timezone
from cogs.league_cog.league_helper.leaderboard_image_pillow import generate_leaderboard_image
from cogs.league_cog.config import (
    LEAGUE_GUILD_ID,
    WINNER_CHANNEL_ID,
    CHAMPION_ROLE_ID,
    ROLES,
    SCORING,
    RATE_LIMITS,
    ROUNDS,
    DISPLAY,
    LANGUAGE
)
from cogs.league_cog.utils import detect_message_language

# Set seed for consistent language detection results
DetectorFactory.seed = LANGUAGE.LANGDETECT_SEED

logger = logging.getLogger(__name__)

# Type variables for decorator
P = ParamSpec('P')
T = TypeVar('T')


def handle_interaction_errors(func: Callable[P, T]) -> Callable[P, T]:
    """
    Decorator for consistent error handling in slash commands.
    Automatically handles exceptions and sends user-friendly error messages.
    """
    @functools.wraps(func)
    async def wrapper(self, interaction: Interaction, *args, **kwargs):
        try:
            return await func(self, interaction, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {e}", exc_info=True)
            error_embed = Embed(
                title="❌ Error",
                description=f"Something went wrong: {str(e)}",
                color=discord.Color.red()
            )
            # Check if we've already responded/deferred
            if interaction.response.is_done():
                await interaction.followup.send(embed=error_embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=error_embed, ephemeral=True)
    return wrapper


class LeagueCog(BaseCog):
    """Cog for managing the opt-in Language League"""

    # Cache TTL in seconds
    LEADERBOARD_CACHE_TTL = 30

    def __init__(self, bot: commands.Bot):
        super().__init__(bot)
        # In-memory cooldown cache: {user_id: {channel_id: timestamp}}
        self.message_cooldowns = {}
        # Leaderboard cache: {cache_key: (data, timestamp)}
        self._leaderboard_cache: dict[str, tuple[list, datetime]] = {}
        self.check_round_end.start()  # Start scheduled task

    async def cog_load(self):
        """Called when cog is loaded - ensure we have an active round"""
        await self.ensure_round_exists()

    def cog_unload(self):
        """Called when cog is unloaded"""
        self.check_round_end.cancel()

    async def get_cached_leaderboard(self, board: str, limit: int) -> list[dict]:
        """Get leaderboard data with caching to reduce DB load"""
        cache_key = f"{board}:{limit}"
        now = datetime.now(timezone.utc)

        # Check if we have valid cached data
        if cache_key in self._leaderboard_cache:
            data, cached_at = self._leaderboard_cache[cache_key]
            age_seconds = (now - cached_at).total_seconds()
            if age_seconds < self.LEADERBOARD_CACHE_TTL:
                logger.debug(f"Leaderboard cache hit for {cache_key} (age: {age_seconds:.1f}s)")
                return data

        # Cache miss or expired - fetch fresh data
        data = await self.bot.db.get_leaderboard(board, limit)
        self._leaderboard_cache[cache_key] = (data, now)
        logger.debug(f"Leaderboard cache miss for {cache_key}, fetched fresh data")
        return data

    def invalidate_leaderboard_cache(self):
        """Clear the leaderboard cache (call after score updates)"""
        self._leaderboard_cache.clear()

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
                await self.process_round_end(current_round)

            # Periodic cleanup of old cooldown entries (prevent memory leak)
            self.cleanup_old_cooldowns()

        except Exception as e:
            logger.error(f"Error in check_round_end task: {e}", exc_info=True)

    @check_round_end.before_loop
    async def before_check_round_end(self):
        """Wait for bot to be ready before starting the round check task"""
        await self.bot.wait_until_ready()

    async def process_round_end(self, current_round: dict) -> dict:
        """
        Full round-end processing: save winners, manage champion roles, announce, create next round.

        Used by both the automated check_round_end task and the manual $league endround command.

        Args:
            current_round: Dict with round info from get_current_round()

        Returns:
            Dict with summary info for the caller (roles_added, roles_removed, next_end, etc.)
        """
        round_id = current_round['round_id']
        round_number = current_round['round_number']

        logger.info(f"Ending round {round_number} (ID: {round_id})")

        # Get guild and champion role
        guild = self.bot.get_guild(LEAGUE_GUILD_ID)
        champion_role = guild.get_role(CHAMPION_ROLE_ID) if guild else None

        if not guild:
            logger.error("Could not find league guild during round end")
        if guild and not champion_role:
            logger.warning(f"Champion role {CHAMPION_ROLE_ID} not found. Continuing without role assignment.")

        # Get users who had the role last round (they're on cooldown)
        last_round_recipients = await self.bot.db.get_last_round_role_recipients()

        # Get top 10 from each league (buffer for skipping cooldown users)
        spanish_top = await self.bot.db.get_leaderboard('spanish', limit=10, round_id=round_id)
        english_top = await self.bot.db.get_leaderboard('english', limit=10, round_id=round_id)

        spanish_top3 = spanish_top[:3]
        english_top3 = english_top[:3]

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
        if winners_data:
            await self.bot.db.save_round_winners(round_id, winners_data)

        # Mark round as completed
        await self.bot.db.end_round(round_id)

        # Determine who gets the champion role (top 3 eligible per league, skipping cooldown)
        spanish_champions = self.get_eligible_champions(spanish_top, last_round_recipients)
        english_champions = self.get_eligible_champions(english_top, last_round_recipients)

        # Collect all new role recipients (deduplicated)
        new_role_recipient_ids = []
        for entry in spanish_champions + english_champions:
            if entry['user_id'] not in new_role_recipient_ids:
                new_role_recipient_ids.append(entry['user_id'])

        # Role management
        roles_added = []
        roles_removed = []

        if champion_role and guild:
            # Remove role from last round's recipients
            for user_id in last_round_recipients:
                try:
                    member = guild.get_member(user_id)
                    if member and champion_role in member.roles:
                        await member.remove_roles(champion_role, reason=f"Round {round_number} ended - champion cooldown")
                        roles_removed.append(user_id)
                except Exception as e:
                    logger.error(f"Failed to remove champion role from {user_id}: {e}")

            # Add role to new champions
            for user_id in new_role_recipient_ids:
                try:
                    member = guild.get_member(user_id)
                    if member and champion_role not in member.roles:
                        await member.add_roles(champion_role, reason=f"Round {round_number} champion")
                        roles_added.append(user_id)
                except Exception as e:
                    logger.error(f"Failed to add champion role to {user_id}: {e}")

        # Track role recipients in database
        if new_role_recipient_ids:
            await self.bot.db.mark_role_recipients(round_id, new_role_recipient_ids)

        # Announce winners in the winner channel
        await self._announce_round_winners(
            round_number=round_number,
            spanish_top3=spanish_top3,
            english_top3=english_top3,
            spanish_champions=spanish_champions,
            english_champions=english_champions,
            last_round_recipients=last_round_recipients
        )

        # Create next round ending next Sunday at 12:00 UTC
        now = datetime.now(timezone.utc)
        days_until_sunday = (6 - now.weekday()) % 7
        if days_until_sunday == 0:
            days_until_sunday = 7
        next_sunday = now + timedelta(days=days_until_sunday)
        next_end = next_sunday.replace(hour=12, minute=0, second=0, microsecond=0)
        next_start = now

        next_round_id = await self.bot.db.create_round(round_number + 1, next_start, next_end)
        logger.info(f"Created next round {round_number + 1} (ID: {next_round_id}): {next_start} to {next_end}")

        # Invalidate leaderboard cache
        self.invalidate_leaderboard_cache()

        return {
            'round_number': round_number,
            'spanish_top3': spanish_top3,
            'english_top3': english_top3,
            'roles_added': roles_added,
            'roles_removed': roles_removed,
            'next_round_number': round_number + 1,
            'next_end': next_end,
        }

    @staticmethod
    def get_eligible_champions(top_list: list, cooldown_set: set, count: int = 3) -> list:
        """Get top N users from a leaderboard who aren't on cooldown."""
        eligible = []
        for entry in top_list:
            if entry['user_id'] not in cooldown_set:
                eligible.append(entry)
                if len(eligible) >= count:
                    break
        return eligible

    @staticmethod
    def build_round_end_announcement(
        round_number: int,
        spanish_top3: list,
        english_top3: list,
        spanish_champions: list,
        english_champions: list,
        last_round_recipients: set
    ) -> str:
        """
        Build the round-end announcement message text.

        Returns the plain-text message string (used by both the real
        announcement and the preview command).
        """
        medals = ["🥇", "🥈", "🥉"]

        lines = [
            f"# 🏆 Round {round_number} has ended! 🏆",
            "",
            "Congratulations to this week's top performers!",
            ""
        ]

        # Spanish League Winners
        if spanish_top3:
            lines.append("## 🇪🇸 Spanish League")
            for i, entry in enumerate(spanish_top3):
                on_cooldown = " *(resting)*" if entry['user_id'] in last_round_recipients else ""
                lines.append(f"{medals[i]} <@{entry['user_id']}> — **{entry['total_score']}** pts{on_cooldown}")
            lines.append("")

        # English League Winners
        if english_top3:
            lines.append("## 🇬🇧 English League")
            for i, entry in enumerate(english_top3):
                on_cooldown = " *(resting)*" if entry['user_id'] in last_round_recipients else ""
                lines.append(f"{medals[i]} <@{entry['user_id']}> — **{entry['total_score']}** pts{on_cooldown}")
            lines.append("")

        # Weekly Champions (role recipients)
        champion_mentions = []
        seen_ids = set()
        for entry in spanish_champions + english_champions:
            if entry['user_id'] not in seen_ids:
                champion_mentions.append(f"<@{entry['user_id']}>")
                seen_ids.add(entry['user_id'])

        if champion_mentions:
            lines.append("## ⭐ Weekly Champions ⭐")
            lines.append(f"This week's <@&{CHAMPION_ROLE_ID}> goes to:")
            lines.append(", ".join(champion_mentions))
            lines.append("")
            lines.append("-# To keep things fair, champions take a 1-week break before they can earn the role again — but they can still compete for the top spots!")
            lines.append("")

        lines.append(f"*Round {round_number} • See you next round!* 🔥")
        lines.append("-# Run `$help league` for more info")

        return "\n".join(lines)

    async def _announce_round_winners(
        self,
        round_number: int,
        spanish_top3: list,
        english_top3: list,
        spanish_champions: list,
        english_champions: list,
        last_round_recipients: set
    ):
        """Send the round-end announcement to the winner channel."""
        try:
            channel = self.bot.get_channel(WINNER_CHANNEL_ID)
            if not channel:
                logger.error(f"Could not find winner announcement channel {WINNER_CHANNEL_ID}")
                return

            message = self.build_round_end_announcement(
                round_number=round_number,
                spanish_top3=spanish_top3,
                english_top3=english_top3,
                spanish_champions=spanish_champions,
                english_champions=english_champions,
                last_round_recipients=last_round_recipients
            )
            await channel.send(message)
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
        # Defer immediately - DB and image generation take time
        await interaction.response.defer()

        try:
            # Get current round info
            current_round = await self.bot.db.get_current_round()
            if not current_round:
                embed = Embed(
                    title="ℹ️ No Active Round",
                    description="There is no active league round at the moment.",
                    color=discord.Color.orange()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # Get top entries for image (use cache if available)
            rankings = await self.get_cached_leaderboard(board, SCORING.LEADERBOARD_DISPLAY_LIMIT)

            if not rankings:
                embed = Embed(
                    title=f"📊 {board.title()} League",
                    description="No users in this league yet!\n\nUse `/league join` to be the first!",
                    color=discord.Color.blue()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # Batch query: get all previous winners at once (instead of N queries)
            user_ids = [entry['user_id'] for entry in rankings]
            previous_winners = await self.bot.db.get_previous_winners(user_ids)

            # Enrich leaderboard data with avatars and winner status
            enriched_data = []
            for entry in rankings:
                try:
                    # Fetch member to get avatar
                    member = interaction.guild.get_member(entry['user_id'])
                    if member and member.display_avatar:
                        avatar_url = str(member.display_avatar.url)
                    else:
                        # Fallback to default Discord avatar
                        default_num = entry['user_id'] % 5
                        avatar_url = f"https://cdn.discordapp.com/embed/avatars/{default_num}.png"

                    enriched_data.append({
                        'rank': entry['rank'],
                        'user_id': entry['user_id'],
                        'username': entry['username'],
                        'total_score': entry['total_score'],
                        'active_days': entry['active_days'],
                        'avatar_url': avatar_url,
                        'is_previous_winner': entry['user_id'] in previous_winners
                    })
                except Exception as e:
                    logger.error(f"Error enriching user {entry['user_id']}: {e}")
                    # Add entry with default avatar on error
                    default_num = entry['user_id'] % 5
                    enriched_data.append({
                        'rank': entry['rank'],
                        'user_id': entry['user_id'],
                        'username': entry['username'],
                        'total_score': entry['total_score'],
                        'active_days': entry['active_days'],
                        'avatar_url': f"https://cdn.discordapp.com/embed/avatars/{default_num}.png",
                        'is_previous_winner': False
                    })

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

            # Generate leaderboard image
            image_path = generate_leaderboard_image(
                leaderboard_data=enriched_data,
                board_type=board,
                round_info={
                    'round_number': current_round['round_number'],
                    'end_date': current_round['end_date']
                }
            )

            # Create embed
            board_emoji = DISPLAY.get_emoji(board)
            board_title = DISPLAY.get_name(board)
            embed = Embed(
                title=f"{board_emoji} {board_title}",
                color=discord.Color.gold()
            )

            # Set the leaderboard image in the embed
            file = File(image_path, filename="leaderboard.png")
            embed.set_image(url="attachment://leaderboard.png")

            # Add requester's rank if outside top rankings
            if requester_stats and requester_stats['rank'] > SCORING.LEADERBOARD_DISPLAY_LIMIT:
                requester_has_won = requester_stats['user_id'] in previous_winners or await self.bot.db.has_user_won_before(requester_stats['user_id'])
                star = "⭐ " if requester_has_won else ""
                embed.add_field(
                    name="📍 Your Rank",
                    value=f"{star}**#{requester_stats['rank']}** • {requester_stats['total_score']} pts • {requester_stats['active_days']} active days",
                    inline=False
                )

            # Show round end date in footer
            end_date = current_round['end_date']
            if end_date.tzinfo is None:
                end_date = end_date.replace(tzinfo=timezone.utc)

            embed.set_footer(text=f"Round {current_round['round_number']} • Ends: {end_date.strftime('%Y-%m-%d %H:%M')} UTC")

            # Send embed with image attached
            await interaction.followup.send(file=file, embed=embed)

            # Clean up temp file
            Path(image_path).unlink(missing_ok=True)

            logger.info(f"User {interaction.user} viewed {board} league (Pillow image)")

        except Exception as e:
            logger.error(f"Error viewing league: {e}", exc_info=True)
            embed = Embed(
                title="❌ Error",
                description=f"Failed to load league: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

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
            detected_lang = detect_message_language(message.content)
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
                round_id=current_round['round_id'],
                message_id=message.id
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

    def cleanup_old_cooldowns(self):
        """Remove expired cooldown entries to prevent memory leak"""
        # Remove entries older than 2x the cooldown period (well expired)
        cutoff = time.time() - (RATE_LIMITS.MESSAGE_COOLDOWN_SECONDS * 2)

        for user_id in list(self.message_cooldowns.keys()):
            for channel_id in list(self.message_cooldowns[user_id].keys()):
                if self.message_cooldowns[user_id][channel_id] < cutoff:
                    del self.message_cooldowns[user_id][channel_id]

            # Remove user entry if no channels remain
            if not self.message_cooldowns[user_id]:
                del self.message_cooldowns[user_id]


async def setup(bot):
    """Setup function to add the cog to the bot"""
    # Load main league cog
    await bot.add_cog(LeagueCog(bot))
    logger.info("LeagueCog loaded successfully")

    # Load admin cog
    from cogs.league_cog.admin import LeagueAdminCog
    await bot.add_cog(LeagueAdminCog(bot))
    logger.info("LeagueAdminCog loaded successfully")
