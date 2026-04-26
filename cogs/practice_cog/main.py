"""
Vocab Practice Cog with SRS (Clozemaster-style)

Provides spaced repetition practice with cloze sentences.
"""
import logging
import unicodedata

import discord
from discord import Embed, Interaction, app_commands
from discord.ext import commands

from base_cog import BaseCog

from .gemini import PracticeGeminiClient
from .seed_words import SEED_WORDS
from .session import PracticeCard, PracticeMode, PracticeSession
from .srs import review_card
from .views import (
    build_question_view,
    build_result_view,
    build_summary_view,
    create_stats_embed,
)

logger = logging.getLogger(__name__)


def _normalize(text: str) -> str:
    """Normalize text for answer comparison: strip accents and lowercase."""
    nfkd = unicodedata.normalize("NFKD", text.strip().lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))

class PracticeCog(BaseCog):
    """Vocabulary practice with spaced repetition."""

    SESSION_TTL = 1800  # 30 minutes
    MAX_SESSIONS = 50

    def __init__(self, bot: commands.Bot):
        super().__init__(bot)
        self.active_sessions: dict[int, PracticeSession] = {}

        try:
            self.gemini = PracticeGeminiClient(api_key=bot.settings.gemini_api_key)
            logger.info("PracticeCog initialized successfully")
        except ValueError as e:
            logger.error("Failed to initialize PracticeCog: %s", e)
            raise

    def _purge_stale_sessions(self) -> None:
        """Remove sessions older than SESSION_TTL."""
        import time
        now = time.time()
        stale = [uid for uid, s in self.active_sessions.items() if now - s.created_at > self.SESSION_TTL]
        for uid in stale:
            del self.active_sessions[uid]
        if stale:
            logger.info("Purged %s stale practice sessions", len(stale))

    # ========================
    # Admin Commands
    # ========================

    @commands.command(name='practice')
    @commands.has_permissions(manage_messages=True)
    async def practice_admin(self, ctx, action: str | None = None, language: str | None = None, count: int = 10):
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

        existing_cards = await self.bot.db.get_cards_for_language(language)
        existing_words = {card['word'] for card in existing_cards}
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
            if word in existing_words:
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
                    existing_words.add(word)
                    logger.info("Created practice card for '%s' (%s)", word, language)

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

    @practice_group.command(name="start", description="Start a tracked practice session (spaced repetition)")
    @app_commands.describe(
        language="Language to practice (spanish or english)",
        level="Difficulty level",
        mode="Practice mode: multiple choice (default) or typing",
    )
    @app_commands.choices(
        language=[
            app_commands.Choice(name="Spanish", value="spanish"),
            app_commands.Choice(name="English", value="english"),
        ],
        level=[
            app_commands.Choice(name="X — All Levels", value="X"),
            app_commands.Choice(name="A — Beginner", value="A"),
            app_commands.Choice(name="B — Intermediate", value="B"),
            app_commands.Choice(name="C — Advanced", value="C"),
        ],
        mode=[
            app_commands.Choice(name="Multiple choice", value="choice"),
            app_commands.Choice(name="Typing", value="typing"),
        ]
    )
    async def practice_start(self, interaction: Interaction, language: str,
                             level: str = "A", mode: str = "choice"):
        """Start a tracked practice session with spaced repetition."""
        await self._begin_session(interaction, language, level, mode, tracked=True)

    @practice_group.command(name="quick", description="Quick practice — no progress tracking")
    @app_commands.describe(
        language="Language to practice (spanish or english)",
        level="Difficulty level",
        mode="Practice mode: multiple choice (default) or typing",
    )
    @app_commands.choices(
        language=[
            app_commands.Choice(name="Spanish", value="spanish"),
            app_commands.Choice(name="English", value="english"),
        ],
        level=[
            app_commands.Choice(name="X — All Levels", value="X"),
            app_commands.Choice(name="A — Beginner", value="A"),
            app_commands.Choice(name="B — Intermediate", value="B"),
            app_commands.Choice(name="C — Advanced", value="C"),
        ],
        mode=[
            app_commands.Choice(name="Multiple choice", value="choice"),
            app_commands.Choice(name="Typing", value="typing"),
        ]
    )
    async def practice_quick(self, interaction: Interaction, language: str,
                             level: str = "A", mode: str = "choice"):
        """Start a quick practice session without spaced repetition tracking."""
        await self._begin_session(interaction, language, level, mode, tracked=False)

    async def _begin_session(self, interaction: Interaction, language: str,
                             level: str, mode: str, *, tracked: bool):
        """Shared session startup logic."""
        user_id = interaction.user.id
        level_filter = None if level == "X" else level

        # Clean up stale sessions
        self._purge_stale_sessions()

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
        if tracked:
            cards = await self._get_session_cards(user_id, language, level=level_filter, limit=10)
        else:
            cards = await self._get_random_cards(language, level=level_filter, limit=10)

        if not cards:
            await interaction.followup.send(
                f"No practice cards available for {language} level {level}. "
                "An admin needs to seed cards first.",
                ephemeral=True
            )
            return

        # Create session
        practice_mode = PracticeMode(mode)
        session = PracticeSession(
            user_id=user_id,
            language=language,
            mode=practice_mode,
            tracked=tracked,
            cards=cards
        )
        self.active_sessions[user_id] = session

        # Show first question
        await self._show_question(interaction, session, is_first=True)

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
        language: str | None = None
    ):
        """View practice statistics"""
        user_id = interaction.user.id

        if language:
            stats = await self.bot.db.get_practice_stats(user_id, language)
            embed = create_stats_embed(language, stats)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            embeds = []
            for lang in ("spanish", "english"):
                stats = await self.bot.db.get_practice_stats(user_id, lang)
                if stats['total'] > 0:
                    embeds.append(create_stats_embed(lang, stats))
            if embeds:
                await interaction.response.send_message(embeds=embeds, ephemeral=True)
            else:
                await interaction.response.send_message("No practice cards available yet.", ephemeral=True)

    @practice_group.command(name="reset", description="Reset your practice progress")
    @app_commands.describe(language="Language to reset (or leave blank for all)")
    @app_commands.choices(
        language=[
            app_commands.Choice(name="Spanish", value="spanish"),
            app_commands.Choice(name="English", value="english"),
        ]
    )
    async def practice_reset(self, interaction: Interaction, language: str | None = None):
        """Reset practice progress for a language or all languages."""
        user_id = interaction.user.id
        deleted = await self.bot.db.reset_user_progress(user_id, language)
        label = language or "all languages"
        await interaction.response.send_message(
            f"♻️ Reset {deleted} cards for {label}. Your progress starts fresh!",
            ephemeral=True
        )

    # ========================
    # Session Flow Methods
    # ========================

    async def _get_session_cards(self, user_id: int, language: str, limit: int = 10,
                                    level: str | None = None) -> list[PracticeCard]:
        """Get cards for a practice session (due cards first, then new)"""
        cards = []

        # Get due cards first
        due_cards = await self.bot.db.get_due_cards(user_id, language, limit, level=level)
        for card_data in due_cards:
            cards.append(PracticeCard(
                id=card_data['id'],
                word=card_data['word'],
                translation=card_data['translation'],
                language=card_data['language'],
                sentence=card_data['sentence'],
                sentence_with_blank=card_data['sentence_with_blank'],
                card_json=card_data.get('card_json'),
                sentence_translation=card_data.get('sentence_translation') or "",
                level=card_data.get('level') or "",
            ))

        # Fill remaining with new cards
        remaining = limit - len(cards)
        if remaining > 0:
            new_cards = await self.bot.db.get_new_cards(user_id, language, remaining, level=level)
            for card_data in new_cards:
                cards.append(PracticeCard(
                    id=card_data['id'],
                    word=card_data['word'],
                    translation=card_data['translation'],
                    language=card_data['language'],
                    sentence=card_data['sentence'],
                    sentence_with_blank=card_data['sentence_with_blank'],
                    sentence_translation=card_data.get('sentence_translation') or "",
                    level=card_data.get('level') or "",
                ))

        return cards

    async def _get_random_cards(self, language: str, level: str | None = None,
                                limit: int = 10) -> list[PracticeCard]:
        """Get random cards for untracked practice."""
        raw = await self.bot.db.get_random_cards(language, limit, level=level)
        return [
            PracticeCard(
                id=c['id'], word=c['word'], translation=c['translation'],
                language=c['language'], sentence=c['sentence'],
                sentence_with_blank=c['sentence_with_blank'],
                sentence_translation=c.get('sentence_translation') or "",
                level=c.get('level') or "",
            )
            for c in raw
        ]

    async def _show_question(self, interaction: Interaction, session: PracticeSession,
                             *, is_first: bool = False):
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
                session.language, card.word, count=3, level=card.level or None
            )
            # Fall back to typing if not enough distractors
            if len(distractors) < 3:
                card_mode = "typing"

        # Build question view
        view = build_question_view(
            session=session, card=card, card_mode=card_mode, distractors=distractors,
            on_answer=lambda i, a: self._handle_answer(i, session, a),
            on_skip=lambda i: self._handle_skip(i, session),
            on_quit=lambda i: self._handle_quit(i, session),
        )

        if is_first:
            try:
                await interaction.followup.send(view=view, ephemeral=True)
            except discord.HTTPException:
                await interaction.edit_original_response(view=view)
        else:
            try:
                await interaction.response.edit_message(view=view)
            except discord.InteractionResponded:
                await interaction.followup.send(view=view, ephemeral=True)

    async def _handle_answer(self, interaction: Interaction, session: PracticeSession, user_answer: str):
        """Handle a user's answer"""
        card = session.current_card

        if card is None:
            return

        # Check answer (case-insensitive)
        was_correct = _normalize(user_answer) == _normalize(card.word)
        session.record_answer(was_correct)

        # Create result embed
        if session.tracked:
            view = build_result_view(
                card, user_answer, was_correct, tracked=True,
                on_rating=lambda i, q: self._handle_rating(i, session, card, q),
            )
        else:
            session.advance()
            view = build_result_view(
                card, user_answer, was_correct, tracked=False,
                on_next=lambda i: self._show_question(i, session) if not session.is_complete
                else self._end_session(i, session),
                on_quit=lambda i: self._handle_quit(i, session),
            )

        # Send result
        try:
            await interaction.response.edit_message(view=view)
        except discord.InteractionResponded:
            await interaction.followup.send(view=view, ephemeral=True)

    async def _handle_rating(self, interaction: Interaction, session: PracticeSession,
                             card: PracticeCard, quality: int):
        """Handle quality rating and update SRS"""
        card_json, due_iso = review_card(card.card_json, quality)

        # Update database
        await self.bot.db.update_user_progress(
            user_id=session.user_id,
            card_id=card.id,
            card_json=card_json,
            next_review=due_iso,
        )

        # Advance to next card
        session.advance()

        # Show next question or summary
        if session.is_complete:
            await self._end_session(interaction, session)
        else:
            await self._show_question(interaction, session)

    async def _handle_skip(self, interaction: Interaction, session: PracticeSession):
        """Handle skipping a card"""
        session.advance()

        if session.is_complete:
            await self._end_session(interaction, session)
        else:
            await self._show_question(interaction, session)

    async def _handle_quit(self, interaction: Interaction, session: PracticeSession):
        """Handle quitting a session"""
        await self._end_session(interaction, session, quit_early=True)

    async def _end_session(self, interaction: Interaction, session: PracticeSession,
                           quit_early: bool = False):
        """End a practice session and show summary"""
        # Remove from active sessions
        if session.user_id in self.active_sessions:
            del self.active_sessions[session.user_id]

        # Create summary
        if quit_early and session.total_reviewed == 0:
            view = build_summary_view(session, quit_early=True)
        else:
            view = build_summary_view(session, quit_early=quit_early)

        # Send summary (session is over)
        try:
            await interaction.response.edit_message(view=view)
        except discord.InteractionResponded:
            await interaction.followup.send(view=view, ephemeral=True)

    async def cog_command_error(self, ctx, error):
        """Handle command errors"""
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need moderator permissions to use this command.")
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"Command on cooldown. Try again in {error.retry_after:.1f}s.")
        else:
            logger.error("Unhandled error in practice cog: %s", error, exc_info=True)
            await ctx.send("An error occurred. Please try again later.")

async def setup(bot):
    """Required setup function for loading the cog"""
    if not bot.settings.gemini_api_key:
        logger.info("GEMINI_API_KEY not set — PracticeCog will not load")
        return
    await bot.add_cog(PracticeCog(bot))
    logger.info("PracticeCog loaded successfully")
