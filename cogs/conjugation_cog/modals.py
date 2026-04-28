"""Modal for typing answers in conjugation sessions."""
import contextlib
import logging
from collections.abc import Awaitable, Callable

import discord
from discord import Interaction, TextStyle
from discord.ui import Modal, TextInput

logger = logging.getLogger(__name__)


class ConjugationAnswerModal(Modal, title="Conjugate"):
    answer = TextInput(
        label="Type the conjugated form",
        placeholder="e.g. hablo, comiste, vivirán...",
        required=True,
        max_length=100,
        style=TextStyle.short,
    )

    def __init__(self, on_answer: Callable[[Interaction, str], Awaitable[None]]):
        super().__init__()
        self.on_answer_callback = on_answer

    async def on_submit(self, interaction: Interaction):
        try:
            await self.on_answer_callback(interaction, self.answer.value.strip())
        except Exception as e:
            logger.error("Error in conjugation modal: %s", e, exc_info=True)
            with contextlib.suppress(discord.InteractionResponded):
                await interaction.response.send_message(
                    "An error occurred. Please try again.", ephemeral=True,
                )
