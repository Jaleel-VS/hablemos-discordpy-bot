"""
Discord UI Views for practice sessions.
"""
from __future__ import annotations

import discord
from discord.ui import View, Button, button
from discord import Interaction, ButtonStyle, Embed
import logging
import random
from typing import TYPE_CHECKING, Callable, Awaitable, Optional, List

from .modals import AnswerModal
from .srs import QUALITY_AGAIN, QUALITY_HARD, QUALITY_GOOD, QUALITY_EASY

if TYPE_CHECKING:
    from .session import PracticeSession, PracticeCard

logger = logging.getLogger(__name__)


class PracticeView(View):
    """View for displaying a practice question"""

    def __init__(
        self,
        session: PracticeSession,
        card: PracticeCard,
        card_mode: str,  # 'typing' or 'choice'
        distractors: List[str],
        on_answer: Callable[[Interaction, str], Awaitable[None]],
        on_skip: Callable[[Interaction], Awaitable[None]],
        on_quit: Callable[[Interaction], Awaitable[None]],
        timeout: float = 300
    ):
        super().__init__(timeout=timeout)
        self.session = session
        self.card = card
        self.card_mode = card_mode
        self.distractors = distractors
        self.on_answer_callback = on_answer
        self.on_skip_callback = on_skip
        self.on_quit_callback = on_quit

        self._build_buttons()

    def _build_buttons(self):
        """Build the view buttons based on mode"""
        if self.card_mode == "choice" and len(self.distractors) >= 3:
            # Multiple choice mode - create choice buttons
            choices = self.distractors[:3] + [self.card.word]
            random.shuffle(choices)

            for choice in choices:
                btn = Button(
                    label=choice,
                    style=ButtonStyle.primary,
                    custom_id=f"choice_{choice}"
                )
                btn.callback = self._make_choice_callback(choice)
                self.add_item(btn)

            # Add skip and quit on next row
            self._add_control_buttons(row=1)
        else:
            # Typing mode - add answer button
            answer_btn = Button(
                label="Answer",
                style=ButtonStyle.primary,
                custom_id="answer"
            )
            answer_btn.callback = self._answer_button_callback
            self.add_item(answer_btn)

            self._add_control_buttons(row=0)

    def _add_control_buttons(self, row: int):
        """Add skip and quit buttons"""
        skip_btn = Button(
            label="Skip",
            style=ButtonStyle.secondary,
            custom_id="skip",
            row=row
        )
        skip_btn.callback = self._skip_callback
        self.add_item(skip_btn)

        quit_btn = Button(
            label="Quit",
            style=ButtonStyle.danger,
            custom_id="quit",
            row=row
        )
        quit_btn.callback = self._quit_callback
        self.add_item(quit_btn)

    def _make_choice_callback(self, choice: str):
        """Create a callback for a choice button"""
        async def callback(interaction: Interaction):
            await self.on_answer_callback(interaction, choice)
        return callback

    async def _answer_button_callback(self, interaction: Interaction):
        """Open the answer modal for typing"""
        modal = AnswerModal(self.card, self.on_answer_callback)
        await interaction.response.send_modal(modal)

    async def _skip_callback(self, interaction: Interaction):
        """Skip the current card"""
        await self.on_skip_callback(interaction)

    async def _quit_callback(self, interaction: Interaction):
        """Quit the session"""
        await self.on_quit_callback(interaction)


class QualityRatingView(View):
    """View for rating answer quality (SRS feedback)"""

    def __init__(
        self,
        was_correct: bool,
        on_rating: Callable[[Interaction, int], Awaitable[None]],
        timeout: float = 300
    ):
        super().__init__(timeout=timeout)
        self.was_correct = was_correct
        self.on_rating_callback = on_rating

        self._build_buttons()

    def _build_buttons(self):
        """Build rating buttons based on whether answer was correct"""
        if self.was_correct:
            # Show Hard, Good, Easy
            hard_btn = Button(
                label="Hard",
                style=ButtonStyle.secondary,
                custom_id="hard"
            )
            hard_btn.callback = self._make_rating_callback(QUALITY_HARD)
            self.add_item(hard_btn)

            good_btn = Button(
                label="Good",
                style=ButtonStyle.primary,
                custom_id="good"
            )
            good_btn.callback = self._make_rating_callback(QUALITY_GOOD)
            self.add_item(good_btn)

            easy_btn = Button(
                label="Easy",
                style=ButtonStyle.success,
                custom_id="easy"
            )
            easy_btn.callback = self._make_rating_callback(QUALITY_EASY)
            self.add_item(easy_btn)
        else:
            # Show only Again
            again_btn = Button(
                label="Again",
                style=ButtonStyle.danger,
                custom_id="again"
            )
            again_btn.callback = self._make_rating_callback(QUALITY_AGAIN)
            self.add_item(again_btn)

    def _make_rating_callback(self, quality: int):
        """Create a callback for a rating button"""
        async def callback(interaction: Interaction):
            await self.on_rating_callback(interaction, quality)
        return callback


def create_question_embed(session: PracticeSession, card: PracticeCard,
                          show_disclaimer: bool = False) -> Embed:
    """Create an embed for a practice question"""
    lang_emoji = {"spanish": "ES", "english": "EN"}.get(session.language, "")

    embed = Embed(
        title=f"Practice ({session.progress_text})",
        description=f"**{card.sentence_with_blank}**",
        color=discord.Color.blue()
    )

    if show_disclaimer:
        embed.add_field(
            name="Beta Feature",
            value="This feature is new and being prototyped. Please contact the server owner for feedback or questions.",
            inline=False
        )

    embed.set_footer(text=f"{lang_emoji} {session.language.title()}")

    return embed


def create_result_embed(card: PracticeCard, user_answer: str, was_correct: bool) -> Embed:
    """Create an embed showing the result of an answer"""
    if was_correct:
        embed = Embed(
            title="Correct!",
            color=discord.Color.green()
        )
        # Show full sentence with word highlighted
        highlighted = card.sentence.replace(
            card.word,
            f"**{card.word}**"
        )
        embed.description = highlighted
    else:
        embed = Embed(
            title="Not quite",
            color=discord.Color.red()
        )
        embed.description = (
            f"Your answer: **{user_answer}**\n"
            f"Correct: **{card.word}**\n\n"
            f"{card.sentence.replace(card.word, f'**{card.word}**')}"
        )

    # Add translation
    embed.add_field(
        name=card.word,
        value=card.translation,
        inline=False
    )

    return embed


def create_summary_embed(session: PracticeSession) -> Embed:
    """Create a session summary embed"""
    percentage = (session.correct_count / session.total_reviewed * 100) if session.total_reviewed > 0 else 0

    embed = Embed(
        title="Session Complete!",
        color=discord.Color.gold()
    )

    embed.add_field(
        name="Score",
        value=f"{session.correct_count}/{session.total_reviewed} ({percentage:.0f}%)",
        inline=True
    )
    embed.add_field(
        name="Cards reviewed",
        value=str(session.total_reviewed),
        inline=True
    )

    return embed


def create_stats_embed(language: str, stats: dict) -> Embed:
    """Create an embed showing practice statistics"""
    lang_emoji = {"spanish": "ES", "english": "EN"}.get(language, "")

    embed = Embed(
        title=f"Practice Stats - {lang_emoji} {language.title()}",
        color=discord.Color.blue()
    )

    embed.add_field(name="New", value=str(stats['new']), inline=True)
    embed.add_field(name="Learning", value=str(stats['learning']), inline=True)
    embed.add_field(name="Due", value=str(stats['due']), inline=True)
    embed.add_field(name="Mastered", value=str(stats['mastered']), inline=True)
    embed.add_field(name="Total Cards", value=str(stats['total']), inline=True)

    return embed
