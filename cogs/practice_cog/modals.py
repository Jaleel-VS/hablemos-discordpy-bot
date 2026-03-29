"""
Modal for typing answers in practice sessions.
"""
from __future__ import annotations

import contextlib
import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import discord
from discord import Interaction, TextStyle
from discord.ui import Modal, TextInput

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
            logger.error("Error in answer modal: %s", e, exc_info=True)
            with contextlib.suppress(discord.InteractionResponded):
                await interaction.response.send_message(
                    "An error occurred. Please try again.",
                    ephemeral=True
                )
