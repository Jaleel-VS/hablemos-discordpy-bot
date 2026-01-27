"""
Vocab Practice Cog with SRS (Clozemaster-style)

Provides spaced repetition practice with cloze sentences.
"""
import logging
import discord
from discord.ext import commands
from discord import app_commands, Interaction, Embed
from typing import Dict, Optional

from base_cog import BaseCog
from .session import PracticeSession, PracticeCard, PracticeMode
from .srs import calculate_sm2, QUALITY_AGAIN
from .views import (
    PracticeView, QualityRatingView,
    create_question_embed, create_result_embed,
    create_summary_embed, create_stats_embed
)
from .gemini import PracticeGeminiClient
from .seed_words import SEED_WORDS

logger = logging.getLogger(__name__)


class PracticeCog(BaseCog):
    """Cog for SRS vocabulary practice"""

    def __init__(self, bot: commands.Bot):
        super().__init__(bot)
        self.active_sessions: Dict[int, PracticeSession] = {}

        try:
            self.gemini = PracticeGeminiClient()
            logger.info("PracticeCog initialized successfully")
        except ValueError as e:
            logger.error(f"Failed to initialize PracticeCog: {e}")
            raise

    # ========================
    # Admin Commands
    # ========================

    @commands.command(name='practice')
    @commands.has_permissions(manage_messages=True)
    async def practice_admin(self, ctx, action: str = None, language: str = None, count: int = 10):
        """
        Admin command for managing practice cards.

        Usage:
            $practice seed spanish 10  - Generate 10 Spanish practice cards
            $practice seed english 10  - Generate 10 English practice cards
            $practice count spanish    - Show card count for Spanish
        """
        if action is None:
            embed = Embed(
                title="Practice Admin Commands",
                description=(
                    "**$practice seed <language> <count>**\n"
                    "Generate practice cards from seed words.\n"
                    "Languages: spanish, english\n\n"
                    "**$practice count <language>**\n"
                    "Show card count for a language."
                ),
                color=discord.Color.blue()
            )
            await ctx.send(embed=embed)
            return

        if action == "seed":
            await self._seed_cards(ctx, language, count)
        elif action == "count":
            await self._show_card_count(ctx, language)
        else:
            await ctx.send(f"Unknown action: {action}. Use `seed` or `count`.")

    async def _seed_cards(self, ctx, language: str, count: int):
        """Generate practice cards from seed words"""
        if language not in SEED_WORDS:
            await ctx.send(f"Unknown language: {language}. Use `spanish` or `english`.")
            return

        words = SEED_WORDS[language][:count]

        embed = Embed(
            title="Generating Practice Cards",
            description=f"Generating {len(words)} cards for {language}...",
            color=discord.Color.blue()
        )
        progress_msg = await ctx.send(embed=embed)

        success_count = 0
        skip_count = 0

        for i, word_data in enumerate(words):
            word = word_data['word']
            translation = word_data['translation']

            # Check if card already exists
            existing = await self.bot.db.get_cards_for_language(language)
            if any(c['word'] == word for c in existing):
                skip_count += 1
                continue

            # Generate sentence using Gemini
            result = await self.gemini.generate_sentence(word, translation, language)

            if result:
                sentence, sentence_with_blank = result

                # Save to database
                card_id = await self.bot.db.add_practice_card(
                    word=word,
                    translation=translation,
                    language=language,
                    sentence=sentence,
                    sentence_with_blank=sentence_with_blank
                )

                if card_id:
                    success_count += 1
                    logger.info(f"Created practice card for '{word}' ({language})")

            # Update progress
            if (i + 1) % 5 == 0 or i == len(words) - 1:
                embed.description = (
                    f"Progress: {i + 1}/{len(words)}\n"
                    f"Created: {success_count}\n"
                    f"Skipped (duplicate): {skip_count}"
                )
                await progress_msg.edit(embed=embed)

        # Final summary
        embed.title = "Card Generation Complete"
        embed.description = (
            f"**Created:** {success_count} cards\n"
            f"**Skipped (duplicate):** {skip_count}\n"
            f"**Failed:** {len(words) - success_count - skip_count}"
        )
        embed.color = discord.Color.green() if success_count > 0 else discord.Color.orange()
        await progress_msg.edit(embed=embed)

    async def _show_card_count(self, ctx, language: str):
        """Show card count for a language"""
        if language not in ['spanish', 'english']:
            await ctx.send("Use `spanish` or `english`.")
            return

        count = await self.bot.db.get_practice_card_count(language)
        await ctx.send(f"**{language.title()}:** {count} practice cards")

    # ========================
    # User Slash Commands
    # ========================

    practice_group = app_commands.Group(
        name="practice",
        description="Vocabulary practice with spaced repetition"
    )

    @practice_group.command(name="start", description="Start a practice session")
    @app_commands.describe(
        language="Language to practice (spanish or english)",
        mode="Practice mode: mixed (default), typing, or choice"
    )
    @app_commands.choices(
        language=[
            app_commands.Choice(name="Spanish", value="spanish"),
            app_commands.Choice(name="English", value="english"),
        ],
        mode=[
            app_commands.Choice(name="Mixed (typing and choice)", value="mixed"),
            app_commands.Choice(name="Typing only", value="typing"),
            app_commands.Choice(name="Multiple choice only", value="choice"),
        ]
    )
    async def practice_start(
        self,
        interaction: Interaction,
        language: str,
        mode: str = "mixed"
    ):
        """Start a practice session"""
        user_id = interaction.user.id

        # Check for existing session
        if user_id in self.active_sessions:
            await interaction.response.send_message(
                "You already have an active practice session. "
                "Please finish or quit it first.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        # Get cards for session
        cards = await self._get_session_cards(user_id, language, limit=10)

        if not cards:
            await interaction.followup.send(
                f"No practice cards available for {language}. "
                "An admin needs to run `$practice seed {language}` first.",
                ephemeral=True
            )
            return

        # Create session
        practice_mode = PracticeMode(mode)
        session = PracticeSession(
            user_id=user_id,
            language=language,
            mode=practice_mode,
            cards=cards
        )
        self.active_sessions[user_id] = session

        # Show first question
        await self._show_question(interaction, session)

    @practice_group.command(name="stats", description="View your practice statistics")
    @app_commands.describe(
        language="Language to check stats for (optional, shows both if not specified)"
    )
    @app_commands.choices(
        language=[
            app_commands.Choice(name="Spanish", value="spanish"),
            app_commands.Choice(name="English", value="english"),
        ]
    )
    async def practice_stats(
        self,
        interaction: Interaction,
        language: Optional[str] = None
    ):
        """View practice statistics"""
        user_id = interaction.user.id

        if language:
            stats = await self.bot.db.get_practice_stats(user_id, language)
            embed = create_stats_embed(language, stats)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            # Show stats for both languages
            spanish_stats = await self.bot.db.get_practice_stats(user_id, "spanish")
            english_stats = await self.bot.db.get_practice_stats(user_id, "english")

            embed = Embed(
                title="Practice Stats",
                color=discord.Color.blue()
            )

            embed.add_field(
                name="Spanish",
                value=(
                    f"New: {spanish_stats['new']} | "
                    f"Learning: {spanish_stats['learning']} | "
                    f"Due: {spanish_stats['due']} | "
                    f"Mastered: {spanish_stats['mastered']}"
                ),
                inline=False
            )
            embed.add_field(
                name="English",
                value=(
                    f"New: {english_stats['new']} | "
                    f"Learning: {english_stats['learning']} | "
                    f"Due: {english_stats['due']} | "
                    f"Mastered: {english_stats['mastered']}"
                ),
                inline=False
            )

            await interaction.response.send_message(embed=embed, ephemeral=True)

    # ========================
    # Session Flow Methods
    # ========================

    async def _get_session_cards(self, user_id: int, language: str, limit: int = 10) -> list[PracticeCard]:
        """Get cards for a practice session (due cards first, then new)"""
        cards = []

        # Get due cards first
        due_cards = await self.bot.db.get_due_cards(user_id, language, limit)
        for card_data in due_cards:
            cards.append(PracticeCard(
                id=card_data['id'],
                word=card_data['word'],
                translation=card_data['translation'],
                language=card_data['language'],
                sentence=card_data['sentence'],
                sentence_with_blank=card_data['sentence_with_blank'],
                interval_days=card_data.get('interval_days'),
                ease_factor=card_data.get('ease_factor'),
                repetitions=card_data.get('repetitions')
            ))

        # Fill remaining with new cards
        remaining = limit - len(cards)
        if remaining > 0:
            new_cards = await self.bot.db.get_new_cards(user_id, language, remaining)
            for card_data in new_cards:
                cards.append(PracticeCard(
                    id=card_data['id'],
                    word=card_data['word'],
                    translation=card_data['translation'],
                    language=card_data['language'],
                    sentence=card_data['sentence'],
                    sentence_with_blank=card_data['sentence_with_blank'],
                    interval_days=1.0,
                    ease_factor=2.5,
                    repetitions=0
                ))

        return cards

    async def _show_question(self, interaction: Interaction, session: PracticeSession):
        """Show the current question"""
        card = session.current_card

        if card is None or session.is_complete:
            await self._end_session(interaction, session)
            return

        # Determine mode for this card
        card_mode = session.get_mode_for_card()

        # Get distractors for multiple choice
        distractors = []
        if card_mode == "choice":
            distractors = await self.bot.db.get_card_distractors(
                session.language, card.word, count=3
            )
            # Fall back to typing if not enough distractors
            if len(distractors) < 3:
                card_mode = "typing"

        # Create embed and view (show disclaimer on first question only)
        show_disclaimer = session.current_index == 0
        embed = create_question_embed(session, card, show_disclaimer=show_disclaimer)

        view = PracticeView(
            session=session,
            card=card,
            card_mode=card_mode,
            distractors=distractors,
            on_answer=lambda i, a: self._handle_answer(i, session, a),
            on_skip=lambda i: self._handle_skip(i, session),
            on_quit=lambda i: self._handle_quit(i, session)
        )

        # Send or edit message
        try:
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        except discord.HTTPException:
            # If followup fails, try editing
            await interaction.edit_original_response(embed=embed, view=view)

    async def _handle_answer(self, interaction: Interaction, session: PracticeSession, user_answer: str):
        """Handle a user's answer"""
        card = session.current_card

        if card is None:
            return

        # Check answer (case-insensitive)
        was_correct = user_answer.lower().strip() == card.word.lower().strip()
        session.record_answer(was_correct)

        # Create result embed
        embed = create_result_embed(card, user_answer, was_correct)

        # Create rating view
        view = QualityRatingView(
            was_correct=was_correct,
            on_rating=lambda i, q: self._handle_rating(i, session, card, q)
        )

        # Send result
        try:
            await interaction.response.edit_message(embed=embed, view=view)
        except discord.InteractionResponded:
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    async def _handle_rating(self, interaction: Interaction, session: PracticeSession,
                             card: PracticeCard, quality: int):
        """Handle quality rating and update SRS"""
        # Calculate new SRS values
        interval = card.interval_days or 1.0
        ease = card.ease_factor or 2.5
        reps = card.repetitions or 0

        result = calculate_sm2(quality, interval, ease, reps)

        # Update database
        await self.bot.db.update_user_progress(
            user_id=session.user_id,
            card_id=card.id,
            interval_days=result.interval_days,
            ease_factor=result.ease_factor,
            repetitions=result.repetitions,
            next_review=result.next_review
        )

        # Advance to next card
        session.advance()

        # Show next question or summary
        if session.is_complete:
            await self._end_session(interaction, session)
        else:
            await self._show_next_question(interaction, session)

    async def _handle_skip(self, interaction: Interaction, session: PracticeSession):
        """Handle skipping a card"""
        session.advance()

        if session.is_complete:
            await self._end_session(interaction, session)
        else:
            await self._show_next_question(interaction, session)

    async def _handle_quit(self, interaction: Interaction, session: PracticeSession):
        """Handle quitting a session"""
        await self._end_session(interaction, session, quit_early=True)

    async def _show_next_question(self, interaction: Interaction, session: PracticeSession):
        """Show the next question"""
        card = session.current_card

        if card is None:
            await self._end_session(interaction, session)
            return

        # Determine mode for this card
        card_mode = session.get_mode_for_card()

        # Get distractors for multiple choice
        distractors = []
        if card_mode == "choice":
            distractors = await self.bot.db.get_card_distractors(
                session.language, card.word, count=3
            )
            if len(distractors) < 3:
                card_mode = "typing"

        # Create embed and view
        embed = create_question_embed(session, card)

        view = PracticeView(
            session=session,
            card=card,
            card_mode=card_mode,
            distractors=distractors,
            on_answer=lambda i, a: self._handle_answer(i, session, a),
            on_skip=lambda i: self._handle_skip(i, session),
            on_quit=lambda i: self._handle_quit(i, session)
        )

        try:
            await interaction.response.edit_message(embed=embed, view=view)
        except discord.InteractionResponded:
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    async def _end_session(self, interaction: Interaction, session: PracticeSession,
                           quit_early: bool = False):
        """End a practice session and show summary"""
        # Remove from active sessions
        if session.user_id in self.active_sessions:
            del self.active_sessions[session.user_id]

        # Create summary embed
        if quit_early and session.total_reviewed == 0:
            embed = Embed(
                title="Session Ended",
                description="Session quit. No cards were reviewed.",
                color=discord.Color.orange()
            )
        else:
            embed = create_summary_embed(session)
            if quit_early:
                embed.title = "Session Ended Early"

        # Send summary with no view (session is over)
        try:
            await interaction.response.edit_message(embed=embed, view=None)
        except discord.InteractionResponded:
            await interaction.followup.send(embed=embed, ephemeral=True)

    async def cog_command_error(self, ctx, error):
        """Handle command errors"""
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need moderator permissions to use this command.")
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"Command on cooldown. Try again in {error.retry_after:.1f}s.")
        else:
            logger.error(f"Unhandled error in practice cog: {error}", exc_info=True)
            await ctx.send("An error occurred. Please try again later.")


async def setup(bot):
    """Required setup function for loading the cog"""
    await bot.add_cog(PracticeCog(bot))
    logger.info("PracticeCog loaded successfully")
