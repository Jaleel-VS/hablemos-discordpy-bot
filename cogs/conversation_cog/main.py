"""
Language Learning Conversation Cog
Provides AI-generated conversations for Spanish-English language learning
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from base_cog import COLORS, BaseCog
from cogs.utils.gemini import GeminiError

from .config import BATCH_SIZE, DAILY_LIMIT
from .conversation_data import (
    CATEGORIES,
    CATEGORY_ALIASES,
    LANGUAGE_ALIASES,
    LANGUAGES,
    LEVEL_ALIASES,
    LEVELS,
)
from .prompts import CONVERSATION_PROMPT, ConversationInput

if TYPE_CHECKING:
    from hablemos import Hablemos

logger = logging.getLogger(__name__)

class ConversationCog(BaseCog):
    """AI-generated conversations for language practice."""

    def __init__(self, bot: Hablemos):
        super().__init__(bot)
        self._background_tasks: set[asyncio.Task] = set()
        logger.info("ConversationCog initialized successfully")

    def _resolve_args(
        self, language: str | None, level: str | None, category: str | None,
    ) -> dict[str, str] | None:
        """Resolve and validate language/level/category, applying alias lookup and defaults."""
        result: dict[str, str] = {}

        for value, aliases, key, choices in [
            (language, LANGUAGE_ALIASES, 'language', LANGUAGES),
            (level, LEVEL_ALIASES, 'level', LEVELS),
            (category, CATEGORY_ALIASES, 'category', CATEGORIES),
        ]:
            if value is None:
                result[key] = random.choice(list(choices.keys()))
            elif value.lower() in aliases:
                result[key] = aliases[value.lower()]
            else:
                return None

        return result

    @commands.hybrid_command(name='convo', aliases=['conv', 'conversation'])
    @commands.cooldown(1, 10, commands.BucketType.user)
    @app_commands.describe(
        language="Language for the conversation",
        level="Difficulty level",
        category="Conversation topic",
    )
    @app_commands.choices(
        language=[app_commands.Choice(name=v['name'], value=k) for k, v in LANGUAGES.items()],
        level=[app_commands.Choice(name=v['name'], value=k) for k, v in LEVELS.items()],
        category=[app_commands.Choice(name=v['name'], value=k) for k, v in CATEGORIES.items()],
    )
    async def convo(self, ctx: commands.Context, language: str | None = None,
                    level: str | None = None, category: str | None = None):
        """
        Get a language learning conversation.

        Usage (prefix): $convo [language] [level] [category]
        Slash command provides autocomplete for all options.
        """
        async with ctx.typing():
            params = self._resolve_args(language, level, category)

            if params is None:
                embed = discord.Embed(
                    title="❌ Invalid Arguments",
                    description=(
                        "**Usage:** `$convo [language] [level] [category]`\n"
                        "or use `/convo` for autocomplete.\n\n"
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

            # In DMs, ctx.author is a User (no guild_permissions), so default to False.
            guild_perms = getattr(ctx.author, 'guild_permissions', None)
            is_moderator = bool(guild_perms and guild_perms.manage_messages)
            daily_limit = DAILY_LIMIT
            if not is_moderator:
                reserved = await self.bot.db.try_reserve_daily_usage(ctx.author.id, daily_limit)
                if not reserved:
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

            conversation = await self.bot.db.get_random_conversation(
                language, level, category
            )

            if not conversation:
                embed = discord.Embed(
                    title="🔄 Generating Conversations",
                    description=(
                        f"No conversations available for **{language} {level} {category}**.\n"
                        f"Generating {BATCH_SIZE} new conversations... This may take a moment."
                    ),
                    color=0xFFA500
                )
                loading_msg = await ctx.send(embed=embed)

                success = await self.generate_conversations_batch(
                    language, level, category, count=BATCH_SIZE
                )

                if not success:
                    if not is_moderator:
                        await self.bot.db.refund_daily_usage(ctx.author.id)
                    embed.title = "❌ Generation Failed"
                    embed.description = "Failed to generate conversations. Please try again later."
                    embed.color = 0xED4245
                    await loading_msg.edit(embed=embed)
                    return

                conversation = await self.bot.db.get_random_conversation(
                    language, level, category
                )

                await loading_msg.delete()

                if not conversation:
                    if not is_moderator:
                        await self.bot.db.refund_daily_usage(ctx.author.id)
                    await ctx.send("❌ Error retrieving conversation after generation.")
                    return

            await self.bot.db.increment_conversation_usage(conversation['id'])

            needs_regen = await self.bot.db.check_regeneration_needed(
                language, level, category
            )

            if needs_regen:
                task = asyncio.create_task(self.regenerate_conversations(
                    language, level, category
                ))
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.discard)

            remaining_after = None
            if not is_moderator:
                remaining_after = await self.bot.db.get_daily_usage_remaining(ctx.author.id, daily_limit)

            embed = self.format_conversation_embed(conversation, remaining_uses=remaining_after)
            await ctx.send(embed=embed)

    async def generate_conversations_batch(self, language: str, level: str,
                                          category: str, count: int = BATCH_SIZE) -> int:
        """
        Generate a batch of conversations for a specific combo

        Returns: Number of successfully generated conversations
        """
        success_count = 0
        scenarios = CATEGORIES[category]['scenarios'][level]

        gemini = self.bot.gemini
        if gemini is None:
            logger.warning("Gemini unavailable — cannot generate conversations")
            return success_count

        for i in range(count):
            try:
                scenario = random.choice(scenarios)

                try:
                    parsed = await gemini.run(
                        CONVERSATION_PROMPT,
                        ConversationInput(
                            language=language,
                            level=level,
                            category=category,
                            scenario=scenario,
                        ),
                    )
                except GeminiError as e:
                    logger.warning(
                        "Conversation Gemini error %s/%s/%s code=%s: %s",
                        language, level, category, e.code, e.message,
                    )
                    parsed = None

                if parsed is not None:
                    await self.bot.db.add_conversation(
                        language=language,
                        level=level,
                        category=category,
                        scenario_intro=parsed.scenario,
                        speaker1_name=parsed.speaker1,
                        speaker2_name=parsed.speaker2,
                        conversation_text=parsed.conversation,
                    )
                    success_count += 1
                    logger.info("Generated conversation %s/%s for %s/%s/%s", i+1, count, language, level, category)
                else:
                    logger.warning("Failed to generate conversation %s/%s", i+1, count)

            except Exception as e:
                logger.error("Error generating conversation %s/%s: %s", i+1, count, e)
                continue

        return success_count

    async def regenerate_conversations(self, language: str, level: str, category: str):
        """
        Background task to regenerate conversations when all have been used

        This runs asynchronously without blocking the user's request
        """
        try:
            logger.info("Starting regeneration for %s/%s/%s", language, level, category)

            deleted = await self.bot.db.delete_old_conversations(language, level, category)
            logger.info("Deleted %s old conversations", deleted)

            success_count = await self.generate_conversations_batch(
                language, level, category, count=BATCH_SIZE
            )

            logger.info("Regenerated %s/%s conversations for %s/%s/%s", success_count, BATCH_SIZE, language, level, category)

        except Exception as e:
            logger.error("Error in background regeneration: %s", e, exc_info=True)

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

        conversation_text = conversation['conversation_text']

        # Split if too long (Discord limit 1024 per field)
        if len(conversation_text) <= 1000:
            embed.add_field(
                name=f"{conversation['speaker1_name']} ↔️ {conversation['speaker2_name']}",
                value=f"```\n{conversation_text}\n```",
                inline=False
            )
        else:
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

        footer_text = (
            f"{lang_emoji} {conversation['language'].title()} • "
            f"{level_emoji} {conversation['level'].title()} • "
            f"ID: {conversation['id']}"
        )

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

        Generates every language, difficulty, and category using the configured batch size.
        """
        target = len(CATEGORIES) * len(LEVELS) * len(LANGUAGES) * BATCH_SIZE
        confirm_embed = discord.Embed(
            title="⚠️ Generate All Conversations",
            description=(
                f"This will generate **{target} conversations**:\n"
                "• 5 categories (Restaurant, Travel, Shopping, Workplace, Social)\n"
                "• 3 difficulty levels (Beginner, Intermediate, Advanced)\n"
                "• 2 languages (Spanish, English)\n"
                f"• {BATCH_SIZE} variations each\n\n"
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

        progress_embed = discord.Embed(
            title="🔄 Generating Conversations",
            description="Starting generation...",
            color=0x3498db
        )
        progress_msg = await ctx.send(embed=progress_embed)

        total = 0
        failed = 0
        start_time = time.monotonic()

        for language in LANGUAGES:
            for level in LEVELS:
                for category in CATEGORIES:
                    elapsed = int(time.monotonic() - start_time)
                    progress_embed.description = (
                        f"**Progress:** {total}/{target} conversations generated\n"
                        f"**Current:** {language} - {level} - {category}\n"
                        f"**Failed:** {failed}\n"
                        f"**Time elapsed:** {elapsed // 60}m {elapsed % 60}s"
                    )
                    await progress_msg.edit(embed=progress_embed)

                    success_count = await self.generate_conversations_batch(
                        language, level, category, count=BATCH_SIZE
                    )

                    total += success_count
                    failed += (BATCH_SIZE - success_count)

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
        logger.info("Setup complete: %s conversations generated, %s failed", total, failed)

    @commands.command(name='convo_stats', aliases=['convostats'])
    @commands.is_owner()
    async def conversation_stats(self, ctx):
        """Show conversation statistics (Owner only)"""

        total_convos = await self.bot.db.get_conversation_count()

        stats_by_combo = await self.bot.db.get_conversation_stats_by_combo()

        embed = discord.Embed(
            title="📊 Conversation Statistics",
            description=f"**Total Conversations:** {total_convos}",
            color=0x3498db
        )

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

async def setup(bot: Hablemos):
    """Required setup function for loading the cog"""
    if bot.gemini is None:
        logger.info("bot.gemini is None — ConversationCog will not load")
        return
    await bot.add_cog(ConversationCog(bot))
