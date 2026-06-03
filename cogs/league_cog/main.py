"""
Language League Cog
Tracks user activity and maintains league rankings for language learners
"""
import asyncio
import functools
import logging
import time
from collections.abc import Callable
from datetime import UTC, date, datetime

import discord
from discord import Embed, Interaction, Member, app_commands
from discord.ext import commands, tasks
from langdetect import DetectorFactory

from base_cog import BaseCog
from cogs.league_cog.config import (
    DISPLAY,
    LANGUAGE,
    LEAGUE_GUILD_ID,
    RATE_LIMITS,
    ROLES,
    ROUNDS,
    SCORING,
)
from cogs.league_cog.league_helper.leaderboard_image_pillow import (
    generate_leaderboard_image,
)
from cogs.league_cog.rounds import (
    ensure_round_exists,
    process_round_end,
)
from cogs.league_cog.scoring import points_for_message
from cogs.league_cog.utils import detect_message_language
from cogs.league_cog.views import LeagueJoinView

# Set seed for consistent language detection results
DetectorFactory.seed = LANGUAGE.LANGDETECT_SEED

logger = logging.getLogger(__name__)

def handle_interaction_errors[**P, T](func: Callable[P, T]) -> Callable[P, T]:
    """
    Decorator for consistent error handling in slash commands.
    Automatically handles exceptions and sends user-friendly error messages.
    """
    @functools.wraps(func)
    async def wrapper(self, interaction: Interaction, *args, **kwargs):
        try:
            return await func(self, interaction, *args, **kwargs)
        except Exception as e:
            logger.error("Error in %s: %s", func.__name__, e, exc_info=True)
            error_embed = Embed(
                title="❌ Error",
                description="Something went wrong. Please try again later.",
                color=discord.Color.red()
            )
            # Check if we've already responded/deferred
            if interaction.response.is_done():
                await interaction.followup.send(embed=error_embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=error_embed, ephemeral=True)
    return wrapper

class LeagueCog(BaseCog):
    """Compete with other learners and track your language progress."""

    # Cache TTL in seconds
    LEADERBOARD_CACHE_TTL = 30

    def __init__(self, bot: commands.Bot):
        super().__init__(bot)
        # In-memory cooldown cache: (user_id, channel_id) → last_counted_timestamp
        self._cooldowns: dict[tuple[int, int], float] = {}
        # Leaderboard cache: {cache_key: (data, timestamp)}
        self._leaderboard_cache: dict[str, tuple[list, datetime]] = {}
        # In-memory caches to avoid DB hits on every message
        self._opted_in_users: set[int] = set()
        self._banned_users: set[int] = set()
        self._excluded_channels: set[int] = set()
        # Per-user learning languages: {user_id: {'learning_spanish': bool, 'learning_english': bool}}
        # Refreshed on join/leave. Stale on Discord role changes until user re-runs /league join
        # (same staleness as the DB row, so no new bug surface).
        self._user_learning: dict[int, dict[str, bool]] = {}
        # Daily message counter: user_id → (date, count).
        # Resets automatically when the stored date differs from today.
        # On bot restart the count resets — at most a day's worth of extra
        # messages could be counted before the cap kicks in again, acceptable.
        self._daily_counts: dict[int, tuple[date, int]] = {}
        # Current active round, refreshed by the check_round_end task every minute
        # and immediately after a round transition. None until cog_load finishes.
        self._current_round: dict | None = None
        # Register the persistent join-button view once so clicks keep working
        # across restarts (stable custom_id + timeout=None). Guarded so cog
        # reloads don't stack duplicate views in ``bot.persistent_views``.
        if not any(isinstance(v, LeagueJoinView) for v in bot.persistent_views):
            bot.add_view(LeagueJoinView(bot))
        self.check_round_end.start()  # Start scheduled task

    async def cog_load(self):
        """Called when cog is loaded - ensure we have an active round and warm caches"""
        await ensure_round_exists(self.bot)
        await self._warm_caches()

    async def _warm_caches(self):
        """Load opt-in, ban, excluded channel, learning-language, and current-round data into memory"""
        try:
            opted = await self.bot.db.get_all_opted_in_users()
            self._opted_in_users = {r['user_id'] for r in opted}
            self._user_learning = {
                r['user_id']: {
                    'learning_spanish': r['learning_spanish'],
                    'learning_english': r['learning_english'],
                }
                for r in opted
            }

            banned = await self.bot.db.get_all_banned_users()
            self._banned_users = {r['user_id'] for r in banned}

            excluded = await self.bot.db.get_excluded_channels()
            self._excluded_channels = {r['channel_id'] for r in excluded}

            self._current_round = await self.bot.db.get_current_round()

            logger.info(
                "League caches warmed: %s opted-in, %s banned, %s excluded channels, round=%s",
                len(self._opted_in_users),
                len(self._banned_users),
                len(self._excluded_channels),
                self._current_round['round_id'] if self._current_round else None,
            )
        except Exception as e:
            logger.error("Failed to warm league caches: %s", e, exc_info=True)

    def cog_unload(self):
        """Called when cog is unloaded"""
        self.check_round_end.cancel()

    @tasks.loop(minutes=ROUNDS.ROUND_CHECK_INTERVAL_MINUTES)
    async def check_round_end(self):
        """Scheduled task to check if current round has ended."""
        try:
            current_round = await self.bot.db.get_current_round()
            self._current_round = current_round
            if not current_round:
                return

            now = datetime.now(UTC)
            end_date = current_round['end_date']
            if end_date.tzinfo is None:
                end_date = end_date.replace(tzinfo=UTC)

            if now >= end_date:
                logger.info("Round %s has ended, processing...", current_round['round_id'])
                await self._process_round_end(current_round)
                # Round-end creates a new round; refresh the cache immediately
                # so on_message picks it up without waiting for the next tick.
                self._current_round = await self.bot.db.get_current_round()

            self.cleanup_old_cooldowns()
        except Exception as e:
            logger.error("Error in check_round_end task: %s", e, exc_info=True)

    @check_round_end.before_loop
    async def before_check_round_end(self):
        """Wait for bot to be ready before starting the round check task."""
        await self.bot.wait_until_ready()

    async def get_cached_leaderboard(self, board: str, limit: int) -> list[dict]:
        """Get leaderboard data with caching to reduce DB load"""
        cache_key = f"{board}:{limit}"
        now = datetime.now(UTC)

        # Check if we have valid cached data
        if cache_key in self._leaderboard_cache:
            data, cached_at = self._leaderboard_cache[cache_key]
            age_seconds = (now - cached_at).total_seconds()
            if age_seconds < self.LEADERBOARD_CACHE_TTL:
                logger.debug("Leaderboard cache hit for %s (age: %.1fs)", cache_key, age_seconds)
                return data

        # Cache miss or expired - fetch fresh data
        data = await self.bot.db.get_leaderboard(board, limit)
        self._leaderboard_cache[cache_key] = (data, now)
        logger.debug("Leaderboard cache miss for %s, fetched fresh data", cache_key)
        return data

    def invalidate_leaderboard_cache(self):
        """Clear the leaderboard cache (call after score updates)"""
        self._leaderboard_cache.clear()

    async def _process_round_end(self, current_round: dict) -> dict:
        """Delegate to rounds module and invalidate cache."""
        result = await process_round_end(self.bot, current_round)
        self.invalidate_leaderboard_cache()
        return result

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
        user_role_ids = {role.id for role in member.roles}

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

    async def perform_join(self, member: Member) -> Embed:
        """Run the league-join flow for a member and return the result embed.

        Shared between the ``/league join`` slash command and the persistent
        join button so both entry points behave identically. Callers are
        responsible for sending the returned embed (typically ephemerally);
        this method never touches ``interaction.response``.
        """
        # Banned users cannot (re-)join.
        if member.id in self._banned_users:
            return Embed(
                title="❌ Banned from the league",
                description=(
                    "You are currently banned from the Language League and "
                    "cannot join. If you believe this is a mistake, please "
                    "contact a moderator."
                ),
                color=discord.Color.red(),
            )

        # Friendly short-circuit for users already in the league.
        if member.id in self._opted_in_users:
            learning = self._user_learning.get(member.id, {})
            if learning.get('learning_spanish'):
                league_name = "Spanish League 🇪🇸"
            elif learning.get('learning_english'):
                league_name = "English League 🇬🇧"
            else:
                league_name = "Language League"
            return Embed(
                title="✅ You're already in the league!",
                description=(
                    f"You're currently competing in the **{league_name}**.\n\n"
                    f"Use `/league stats` to track your progress or "
                    f"`/league view` to see the leaderboard!"
                ),
                color=discord.Color.green(),
            )

        # Validate roles
        validation = await self.validate_user_roles(member)
        if not validation['valid']:
            return Embed(
                description=validation['error_message'],
                color=discord.Color.red(),
            )

        # Join league (upsert — safe if a stale cache miss happens)
        await self.bot.db.leaderboard_join(
            user_id=member.id,
            username=str(member),
            learning_spanish=validation['learning_spanish'],
            learning_english=validation['learning_english'],
        )

        # Update in-memory cache
        self._opted_in_users.add(member.id)
        self._user_learning[member.id] = {
            'learning_spanish': validation['learning_spanish'],
            'learning_english': validation['learning_english'],
        }
        logger.info("User %s (%s) joined Language League", member, member.id)

        league_name = "Spanish League 🇪🇸" if validation['learning_spanish'] else "English League 🇬🇧"
        language_name = "Spanish" if validation['learning_spanish'] else "English"

        return Embed(
            title="✅ Welcome to the Language League!",
            description=(
                f"You're now competing in the **{league_name}**!\n\n"
                f"📝 **How it works:**\n"
                f"• Only messages in **{language_name}** will count\n"
                f"• Messages must be at least {RATE_LIMITS.MIN_MESSAGE_LENGTH} characters\n"
                f"• {RATE_LIMITS.MESSAGE_COOLDOWN_SECONDS}-second cooldown per channel (no spam!)\n"
                f"• Max {RATE_LIMITS.DAILY_MESSAGE_CAP} counted messages per day\n"
                f"• +{SCORING.ACTIVE_DAY_BONUS_MULTIPLIER} bonus points for each active day\n\n"
                f"Use `/league stats` to track your progress!\n\n"
                f"Good luck! 🎯"
            ),
            color=discord.Color.green(),
        )

    @league_group.command(name="join", description="Join the Language League")
    async def league_join(self, interaction: Interaction):
        """Join the Language League (opt-in)"""
        try:
            embed = await self.perform_join(interaction.user)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error("Error in league join: %s", e, exc_info=True)
            embed = Embed(
                title="❌ Error",
                description="Failed to join Language League. Please try again later.",
                color=discord.Color.red(),
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
            logger.info("User %s (%s) left Language League", interaction.user, interaction.user.id)

            # Update in-memory cache
            self._opted_in_users.discard(interaction.user.id)
            self._user_learning.pop(interaction.user.id, None)

        except Exception as e:
            logger.error("Error in league leave: %s", e, exc_info=True)
            embed = Embed(
                title="❌ Error",
                description="Failed to leave Language League. Please try again later.",
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

            # Enrich leaderboard data with avatars
            enriched_data = []
            for entry in rankings:
                try:
                    member = interaction.guild.get_member(entry['user_id'])
                    if member and member.display_avatar:
                        avatar_url = str(member.display_avatar.url)
                    else:
                        default_num = entry['user_id'] % 5
                        avatar_url = f"https://cdn.discordapp.com/embed/avatars/{default_num}.png"

                    enriched_data.append({
                        'rank': entry['rank'],
                        'user_id': entry['user_id'],
                        'username': entry['username'],
                        'total_score': entry['total_score'],
                        'active_days': entry['active_days'],
                        'avatar_url': avatar_url,
                    })
                except Exception as e:
                    logger.error("Error enriching user %s: %s", entry['user_id'], e)
                    default_num = entry['user_id'] % 5
                    enriched_data.append({
                        'rank': entry['rank'],
                        'user_id': entry['user_id'],
                        'username': entry['username'],
                        'total_score': entry['total_score'],
                        'active_days': entry['active_days'],
                        'avatar_url': f"https://cdn.discordapp.com/embed/avatars/{default_num}.png",
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

            # Generate leaderboard image (returns BytesIO — no temp file needed)
            buf = await asyncio.wait_for(
                asyncio.to_thread(generate_leaderboard_image, enriched_data),
                timeout=30,
            )

            # Caption text shown below the image in the Components V2 container
            board_emoji = DISPLAY.get_emoji(board)
            board_title = DISPLAY.get_name(board)
            end_date = current_round['end_date']
            if end_date.tzinfo is None:
                end_date = end_date.replace(tzinfo=UTC)
            caption_lines = [
                f"## {board_emoji} {board_title}",
                f"-# Round {current_round['round_number']} • Ends {end_date.strftime('%Y-%m-%d %H:%M')} UTC",
            ]
            if requester_stats and requester_stats['rank'] > SCORING.LEADERBOARD_DISPLAY_LIMIT:
                caption_lines.append(
                    f"📍 Your rank: **#{requester_stats['rank']}** "
                    f"• {requester_stats['total_score']} pts "
                    f"• {requester_stats['active_days']} active days"
                )

            file = discord.File(buf, filename="leaderboard.png")
            view = discord.ui.LayoutView()
            view.add_item(discord.ui.Container(
                discord.ui.MediaGallery(
                    discord.MediaGalleryItem(media="attachment://leaderboard.png"),
                ),
                discord.ui.Separator(visible=False),
                discord.ui.TextDisplay("\n".join(caption_lines)),
            ))
            try:
                await interaction.followup.send(view=view, file=file)
            except discord.HTTPException:
                # Components V2 not available — fall back to plain image
                buf.seek(0)
                await interaction.followup.send(file=discord.File(buf, filename="leaderboard.png"))
            logger.info("User %s viewed %s league", interaction.user, board)

        except Exception as e:
            logger.error("Error viewing league: %s", e, exc_info=True)
            embed = Embed(
                title="❌ Error",
                description="Failed to load league. Please try again later.",
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
        user: Member | None = None
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

            embed = Embed(
                title=title,
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
                end_date = end_date.replace(tzinfo=UTC)

            footer_text = f"Round ends: {end_date.strftime('%Y-%m-%d %H:%M')} UTC"
            if is_self and stats['active_days'] > 0:
                footer_text += " • Keep it up! 🔥"

            embed.set_footer(text=footer_text)

            await interaction.response.send_message(embed=embed)
            logger.info("User %s viewed stats for %s", interaction.user, target)

        except Exception as e:
            logger.error("Error viewing stats: %s", e, exc_info=True)
            embed = Embed(
                title="❌ Error",
                description="Failed to load stats. Please try again later.",
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

            # Check caches (no DB hit)
            if message.author.id not in self._opted_in_users:
                return
            if message.author.id in self._banned_users:
                return
            if message.channel.id in self._excluded_channels:
                return

            # Anti-spam: Check message cooldown
            if not self.check_message_cooldown(message.author.id, message.channel.id):
                return  # Too soon, don't count

            # Language detection: Only count messages in the language being learned.
            # Done before the daily-cap DB query because it's free and rejects the
            # majority of messages (short, emoji-only, mixed, undetectable).
            detected_lang = detect_message_language(message.content)
            if not detected_lang:
                return  # Could not detect language or message too short

            # Anti-spam: Check daily cap (in-memory, no DB hit)
            if not self._check_and_increment_daily(message.author.id):
                return  # Hit daily cap

            # Get what language(s) the user is learning (from in-memory cache)
            learning = self._user_learning.get(message.author.id)
            if not learning:
                return  # Not in cache (race with leave); skip

            # Check if message is in the language they're learning
            is_valid_message = False
            if (detected_lang == LANGUAGE.SPANISH_CODE and learning['learning_spanish']) or (detected_lang == LANGUAGE.ENGLISH_CODE and learning['learning_english']):
                is_valid_message = True

            if not is_valid_message:
                return  # Message not in the language they're learning

            # Get current round (from in-memory cache, refreshed by check_round_end task)
            current_round = self._current_round
            if not current_round:
                logger.warning("No active round found, cannot record activity")
                return

            # Record activity
            await self.bot.db.record_activity(
                user_id=message.author.id,
                activity_type='message',
                channel_id=message.channel.id,
                points=points_for_message(message.channel.id),
                round_id=current_round['round_id'],
                message_id=message.id
            )

            # Update cooldown cache
            self.update_message_cooldown(message.author.id, message.channel.id)

        except Exception as e:
            logger.error("Error in league message tracking: %s", e, exc_info=True)

    def _check_and_increment_daily(self, user_id: int) -> bool:
        """Return True if user is under the daily cap, incrementing their count.

        Automatically resets when the stored date differs from today (UTC).
        No DB access.
        """
        today = datetime.now(UTC).date()
        entry = self._daily_counts.get(user_id)
        if entry and entry[0] == today:
            if entry[1] >= RATE_LIMITS.DAILY_MESSAGE_CAP:
                return False
            self._daily_counts[user_id] = (today, entry[1] + 1)
        else:
            self._daily_counts[user_id] = (today, 1)
        return True

    def check_message_cooldown(self, user_id: int, channel_id: int) -> bool:
        """Return True if enough time has passed since the last counted message."""
        ts = self._cooldowns.get((user_id, channel_id))
        return ts is None or (time.time() - ts) >= RATE_LIMITS.MESSAGE_COOLDOWN_SECONDS

    def update_message_cooldown(self, user_id: int, channel_id: int) -> None:
        """Record the current time as the last counted message timestamp."""
        self._cooldowns[(user_id, channel_id)] = time.time()

    def cleanup_old_cooldowns(self) -> None:
        """Evict expired cooldown entries to prevent unbounded memory growth."""
        cutoff = time.time() - RATE_LIMITS.MESSAGE_COOLDOWN_SECONDS * 2
        self._cooldowns = {k: v for k, v in self._cooldowns.items() if v >= cutoff}

async def setup(bot):
    """Setup function to add the cog to the bot"""
    # Load main league cog
    await bot.add_cog(LeagueCog(bot))
    logger.info("LeagueCog loaded successfully")

    # Load admin cog
    from cogs.league_cog.admin import LeagueAdminCog
    await bot.add_cog(LeagueAdminCog(bot))
    logger.info("LeagueAdminCog loaded successfully")
