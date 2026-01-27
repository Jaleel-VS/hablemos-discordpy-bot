"""
Modal for typing answers in practice sessions.
"""
from __future__ import annotations

import discord
from discord.ui import Modal, TextInput
from discord import Interaction, TextStyle
import logging
from typing import TYPE_CHECKING, Callable, Awaitable

if TYPE_CHECKING:
    from .session import PracticeCard

logger = logging.getLogger(__name__)


class AnswerModal(Modal, title="Enter Your Answer"):
    """Modal for typing an answer to a practice question"""

    answer = TextInput(
        label="Fill in the blank",
        placeholder="Type the missing word...",
        required=True,
        max_length=100,
        style=TextStyle.short
    )

    def __init__(self, card: PracticeCard,
                 on_answer: Callable[[Interaction, str], Awaitable[None]]):
        super().__init__()
        self.card = card
        self.on_answer_callback = on_answer

    async def on_submit(self, interaction: Interaction):
        """Called when the modal is submitted"""
        try:
            user_answer = self.answer.value.strip()
            await self.on_answer_callback(interaction, user_answer)
        except Exception as e:
            logger.error(f"Error in answer modal: {e}", exc_info=True)
            try:
                await interaction.response.send_message(
                    "An error occurred. Please try again.",
                    ephemeral=True
                )
            except discord.InteractionResponded:
                pass
