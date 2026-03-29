"""
Language Learning Conversation Cog
Provides AI-generated conversations for Spanish-English language learning
"""
import asyncio
import logging
import random
import time

import discord
from discord.ext import commands

from base_cog import COLORS, BaseCog

from .conversation_data import (
    CATEGORIES,
    CATEGORY_ALIASES,
    LANGUAGE_ALIASES,
    LANGUAGES,
    LEVEL_ALIASES,
    LEVELS,
)
from .gemini_client import ConversationGeminiClient

logger = logging.getLogger(__name__)

class ConversationCog(BaseCog):
    """AI-generated conversations for language practice."""

    def __init__(self, bot):
        super().__init__(bot)
        self._background_tasks: set[asyncio.Task] = set()
        try:
            self.gemini = ConversationGeminiClient(api_key=bot.settings.gemini_api_key)
            logger.info("ConversationCog initialized successfully")
        except ValueError as e:
            logger.error(f"Failed to initialize ConversationCog: {e}")
            raise

    async def parse_convo_args(self, args: tuple) -> dict | None:
        """
        Parse flexible arguments for $convo command

        Supports:
        - spanish, spa, es → 'spanish'
        - beginner, beg, a1 → 'beginner'
        - restaurant, rest, food → 'restaurant'

        Returns dict with 'language', 'level', 'category' or None for invalid
        """
        result = {'language': None, 'level': None, 'category': None}

        for arg in args:
            arg_lower = arg.lower()

            # Try to match language
            if arg_lower in LANGUAGE_ALIASES and result['language'] is None:
                result['language'] = LANGUAGE_ALIASES[arg_lower]
            # Try to match level
            elif arg_lower in LEVEL_ALIASES and result['level'] is None:
                result['level'] = LEVEL_ALIASES[arg_lower]
            # Try to match category
            elif arg_lower in CATEGORY_ALIASES and result['category'] is None:
                result['category'] = CATEGORY_ALIASES[arg_lower]
            else:
                # Invalid argument
                return None

        # Fill in defaults for missing args
        if result['language'] is None:
            result['language'] = random.choice(list(LANGUAGES.keys()))
        if result['level'] is None:
            result['level'] = 'beginner'
        if result['category'] is None:
            result['category'] = random.choice(list(CATEGORIES.keys()))

        return result

    @commands.command(name='convo', aliases=['conv', 'conversation'])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def convo(self, ctx, *args):
        """
        Get a language learning conversation

        Usage:
            $convo                              - Random beginner conversation
            $convo spanish                      - Random Spanish beginner
            $convo english intermediate         - Random English intermediate
            $convo spanish advanced restaurant  - Specific request

        Languages: spanish (spa/es), english (eng/en)
        Levels: beginner (beg), intermediate (int), advanced (adv)
        Categories: restaurant, travel, shopping, workplace, social
        """
        # Send typing indicator
        async with ctx.typing():
            # Parse arguments
            params = await self.parse_convo_args(args)

            if params is None:
                embed = discord.Embed(
                    title="❌ Invalid Arguments",
                    description=(
                        "**Usage:** `$convo [language] [level] [category]`\n\n"
                        "**Examples:**\n"
                        "• `$convo` - Random beginner conversation\n"
                        "• `$convo spanish` - Random Spanish beginner\n"
                        "• `$convo english intermediate restaurant`\n\n"
                        "**Languages:** spanish (spa/es), english (eng/en)\n"
                        "**Levels:** beginner (beg), intermediate (int), advanced (adv)\n"
                        "**Categories:** restaurant, travel, shopping, workplace, social"
                    ),
                    color=0xED4245
                )
                await ctx.send(embed=embed)
                return

            language = params['language']
            level = params['level']
            category = params['category']

            # Check daily limit (2 per day) - moderators are exempt
            is_moderator = ctx.author.guild_permissions.manage_messages
            if not is_moderator:
                daily_limit = 2
                usage = await self.bot.db.check_daily_limit(ctx.author.id, daily_limit)

                if usage >= daily_limit:
                    embed = discord.Embed(
                        title="⏱️ Daily Limit Reached",
                        description=(
                            f"You've reached your daily limit of **{daily_limit} conversations**.\n\n"
                            f"Come back tomorrow for more practice! 📚\n\n"
                            f"*Moderators have unlimited access.*"
                        ),
                        color=0xFFA500
                    )
                    await ctx.send(embed=embed)
                    return

            # Get conversation from database
            conversation = await self.bot.db.get_random_conversation(
                language, level, category
            )

            if not conversation:
                # No conversations exist - generate some
                embed = discord.Embed(
                    title="🔄 Generating Conversations",
                    description=(
                        f"No conversations available for **{language} {level} {category}**.\n"
                        f"Generating 10 new conversations... This may take a moment."
                    ),
                    color=0xFFA500
                )
                loading_msg = await ctx.send(embed=embed)

                # Generate 10 conversations for this combo
                success = await self.generate_conversations_batch(
                    language, level, category, count=10
                )

                if not success:
                    embed.title = "❌ Generation Failed"
                    embed.description = "Failed to generate conversations. Please try again later."
                    embed.color = 0xED4245
                    await loading_msg.edit(embed=embed)
                    return

                # Try again to get a conversation
                conversation = await self.bot.db.get_random_conversation(
                    language, level, category
                )

                await loading_msg.delete()

                if not conversation:
                    await ctx.send("❌ Error retrieving conversation after generation.")
                    return

            # Increment usage count
            await self.bot.db.increment_conversation_usage(conversation['id'])

            # Check if regeneration is needed (all used at least once)
            needs_regen = await self.bot.db.check_regeneration_needed(
                language, level, category
            )

            if needs_regen:
                task = asyncio.create_task(self.regenerate_conversations(
                    language, level, category
                ))
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.discard)

            # Display conversation
            # Calculate remaining uses for display (only for non-moderators)
            remaining_after = None
            if not is_moderator:
                remaining_after = await self.bot.db.get_daily_usage_remaining(ctx.author.id, daily_limit) - 1

            embed = self.format_conversation_embed(conversation, remaining_uses=remaining_after)
            await ctx.send(embed=embed)

            # Increment daily usage count (only for non-moderators)
            if not is_moderator:
                await self.bot.db.increment_daily_usage(ctx.author.id)

    async def generate_conversations_batch(self, language: str, level: str,
                                          category: str, count: int = 10) -> int:
        """
        Generate a batch of conversations for a specific combo

        Returns: Number of successfully generated conversations
        """
        success_count = 0
        scenarios = CATEGORIES[category]['scenarios'][level]

        for i in range(count):
            try:
                # Select random scenario
                scenario = random.choice(scenarios)

                # Generate conversation
                conversation_data = await self.gemini.generate_conversation(
                    language, level, category, scenario
                )

                if conversation_data:
                    # Save to database
                    await self.bot.db.add_conversation(
                        language=language,
                        level=level,
                        category=category,
                        scenario_intro=conversation_data['scenario'],
                        speaker1_name=conversation_data['speaker1'],
                        speaker2_name=conversation_data['speaker2'],
                        conversation_text=conversation_data['conversation']
                    )
                    success_count += 1
                    logger.info(f"Generated conversation {i+1}/{count} for {language}/{level}/{category}")
                else:
                    logger.warning(f"Failed to generate conversation {i+1}/{count}")

                # Rate limiting: 1 second between generations
                if i < count - 1:
                    await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"Error generating conversation {i+1}/{count}: {e}")
                continue

        return success_count

    async def regenerate_conversations(self, language: str, level: str, category: str):
        """
        Background task to regenerate conversations when all have been used

        This runs asynchronously without blocking the user's request
        """
        try:
            logger.info(f"Starting regeneration for {language}/{level}/{category}")

            # Delete old conversations
            deleted = await self.bot.db.delete_old_conversations(language, level, category)
            logger.info(f"Deleted {deleted} old conversations")

            # Generate 10 new ones
            success_count = await self.generate_conversations_batch(
                language, level, category, count=10
            )

            logger.info(f"Regenerated {success_count}/10 conversations for {language}/{level}/{category}")

        except Exception as e:
            logger.error(f"Error in background regeneration: {e}", exc_info=True)

    def format_conversation_embed(self, conversation: dict, remaining_uses: int | None = None) -> discord.Embed:
        """
        Format conversation as a Discord embed

        Args:
            conversation: Conversation dict from database
            remaining_uses: Number of conversations remaining today (None for moderators)
        """
        lang_emoji = LANGUAGES[conversation['language']]['emoji']
        level_emoji = LEVELS[conversation['level']]['emoji']
        category_emoji = CATEGORIES[conversation['category']]['emoji']
        category_name = CATEGORIES[conversation['category']]['name']

        embed = discord.Embed(
            title=f"{category_emoji} {category_name} Conversation",
            description=f"**Scenario:** {conversation['scenario_intro']}",
            color=random.choice(COLORS)
        )

        # Add conversation
        conversation_text = conversation['conversation_text']

        # Split if too long (Discord limit 1024 per field)
        if len(conversation_text) <= 1000:
            embed.add_field(
                name=f"{conversation['speaker1_name']} ↔️ {conversation['speaker2_name']}",
                value=f"```\n{conversation_text}\n```",
                inline=False
            )
        else:
            # Split into chunks at natural break points (by line)
            lines = conversation_text.split('\n')
            current_chunk = []
            chunks = []
            current_length = 0

            for line in lines:
                line_length = len(line) + 1
                if current_length + line_length > 900 and current_chunk:
                    chunks.append('\n'.join(current_chunk))
                    current_chunk = [line]
                    current_length = line_length
                else:
                    current_chunk.append(line)
                    current_length += line_length

            if current_chunk:
                chunks.append('\n'.join(current_chunk))

            for i, chunk in enumerate(chunks):
                field_name = f"{conversation['speaker1_name']} ↔️ {conversation['speaker2_name']}" if i == 0 else "..."
                embed.add_field(
                    name=field_name,
                    value=f"```\n{chunk}\n```",
                    inline=False
                )

        # Footer with metadata
        footer_text = (
            f"{lang_emoji} {conversation['language'].title()} • "
            f"{level_emoji} {conversation['level'].title()} • "
            f"ID: {conversation['id']}"
        )

        # Add remaining uses info for non-moderators
        if remaining_uses is not None:
            if remaining_uses > 0:
                footer_text += f" • {remaining_uses} remaining today"
            else:
                footer_text += " • Last one for today!"

        embed.set_footer(text=footer_text)

        return embed

    @commands.command(name='setup_convos')
    @commands.has_permissions(manage_messages=True)
    async def setup_conversations(self, ctx):
        """
        Generate all initial conversations (Moderators/Owner only)

        Generates: 5 categories × 3 levels × 2 languages × 10 conversations = 300 total
        This command can take 10-15 minutes to complete.
        """
        # Confirm with user
        confirm_embed = discord.Embed(
            title="⚠️ Generate All Conversations",
            description=(
                "This will generate **300 conversations**:\n"
                "• 5 categories (Restaurant, Travel, Shopping, Workplace, Social)\n"
                "• 3 difficulty levels (Beginner, Intermediate, Advanced)\n"
                "• 2 languages (Spanish, English)\n"
                "• 10 variations each\n\n"
                "**This will take approximately 10-15 minutes.**\n\n"
                "React with ✅ to confirm or ❌ to cancel."
            ),
            color=0xFFA500
        )

        confirm_msg = await ctx.send(embed=confirm_embed)
        await confirm_msg.add_reaction('✅')
        await confirm_msg.add_reaction('❌')

        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ['✅', '❌'] and reaction.message.id == confirm_msg.id

        try:
            reaction, _user = await self.bot.wait_for('reaction_add', timeout=30.0, check=check)
        except TimeoutError:
            await confirm_msg.edit(embed=discord.Embed(
                title="❌ Setup Cancelled",
                description="Setup cancelled (timeout)",
                color=0xED4245
            ))
            return

        if str(reaction.emoji) == '❌':
            await confirm_msg.edit(embed=discord.Embed(
                title="❌ Setup Cancelled",
                description="Setup cancelled by user",
                color=0xED4245
            ))
            return

        # Start generation
        progress_embed = discord.Embed(
            title="🔄 Generating Conversations",
            description="Starting generation...",
            color=0x3498db
        )
        progress_msg = await ctx.send(embed=progress_embed)

        total = 0
        failed = 0
        start_time = time.monotonic()

        # Generate for each combination
        for language in LANGUAGES:
            for level in LEVELS:
                for category in CATEGORIES:
                    # Update progress
                    elapsed = int(time.monotonic() - start_time)
                    progress_embed.description = (
                        f"**Progress:** {total}/300 conversations generated\n"
                        f"**Current:** {language} - {level} - {category}\n"
                        f"**Failed:** {failed}\n"
                        f"**Time elapsed:** {elapsed // 60}m {elapsed % 60}s"
                    )
                    await progress_msg.edit(embed=progress_embed)

                    # Generate 10 conversations for this combo
                    success_count = await self.generate_conversations_batch(
                        language, level, category, count=10
                    )

                    total += success_count
                    failed += (10 - success_count)

                    # Rate limiting: wait 2 seconds between batches
                    await asyncio.sleep(2)

        # Final report
        elapsed_time = int(time.monotonic() - start_time)
        final_embed = discord.Embed(
            title="✅ Conversation Generation Complete",
            description=(
                f"**Generated:** {total} conversations\n"
                f"**Failed:** {failed}\n"
                f"**Time taken:** {elapsed_time // 60}m {elapsed_time % 60}s\n\n"
                f"Users can now use `$convo` to get conversations!"
            ),
            color=0x00FF00 if failed == 0 else 0xFFA500
        )

        await progress_msg.edit(embed=final_embed)
        logger.info(f"Setup complete: {total} conversations generated, {failed} failed")

    @commands.command(name='convo_stats', aliases=['convostats'])
    @commands.is_owner()
    async def conversation_stats(self, ctx):
        """Show conversation statistics (Owner only)"""

        # Get total counts
        total_convos = await self.bot.db.get_conversation_count()

        # Get breakdown by combo
        stats_by_combo = await self.bot.db.get_conversation_stats_by_combo()

        embed = discord.Embed(
            title="📊 Conversation Statistics",
            description=f"**Total Conversations:** {total_convos}",
            color=0x3498db
        )

        # Group by language
        for language in LANGUAGES:
            lang_stats = [s for s in stats_by_combo if s['language'] == language]

            if lang_stats:
                lang_emoji = LANGUAGES[language]['emoji']
                stats_text = ""

                for stat in lang_stats:
                    level_emoji = LEVELS[stat['level']]['emoji']
                    cat_emoji = CATEGORIES[stat['category']]['emoji']

                    stats_text += (
                        f"{level_emoji} {stat['level'].title()} - "
                        f"{cat_emoji} {stat['category'].title()}: "
                        f"{stat['count']} convos "
                        f"(avg use: {stat['avg_usage']:.1f})\n"
                    )

                embed.add_field(
                    name=f"{lang_emoji} {language.title()}",
                    value=stats_text or "No conversations",
                    inline=False
                )

        await ctx.send(embed=embed)

    async def cog_command_error(self, ctx, error):
        """Handle command errors"""
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You need moderator permissions (Manage Messages) to use this command.")
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"⏱️ Command on cooldown. Try again in {error.retry_after:.1f} seconds.")
        elif isinstance(error, commands.CheckFailure):
            await ctx.send("❌ You don't have permission to use this command.")
        else:
            logger.error(f"Unhandled error in conversation cog: {error}", exc_info=True)
            await ctx.send("❌ An error occurred. Please try again later.")

async def setup(bot):
    """Required setup function for loading the cog"""
    await bot.add_cog(ConversationCog(bot))
