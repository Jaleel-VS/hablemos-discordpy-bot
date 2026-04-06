"""Reusable public/private visibility chooser for command results."""
import contextlib
from collections.abc import Awaitable, Callable

import discord


class VisibilityView(discord.ui.View):
    """Buttons that let the command author choose public or private delivery.

    Parameters
    ----------
    author_id: The user allowed to interact with the buttons.
    command_message: The original command invocation message.
    on_public: ``async def(channel) -> None`` — send the result publicly.
    on_private: ``async def(interaction) -> None`` — send the result ephemerally.
    """

    def __init__(
        self,
        *,
        author_id: int,
        command_message: discord.Message,
        on_public: Callable[[discord.TextChannel], Awaitable[None]],
        on_private: Callable[[discord.Interaction], Awaitable[None]],
        timeout: float = 120,
    ):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.command_message = command_message
        self._on_public = on_public
        self._on_private = on_private
        self.prompt_message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author_id

    @discord.ui.button(label='Send Public', style=discord.ButtonStyle.primary)
    async def send_public(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()
        try:
            await self._on_public(self.command_message)
        except (discord.NotFound, discord.HTTPException):
            await self._on_public(None)
        self.stop()

    @discord.ui.button(label='Send Private', style=discord.ButtonStyle.secondary)
    async def send_private(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._on_private(interaction)
        await interaction.message.delete()
        with contextlib.suppress(discord.NotFound, discord.HTTPException):
            await self.command_message.delete()
        self.stop()

    @discord.ui.button(label='Discard', style=discord.ButtonStyle.danger)
    async def discard(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()
        self.stop()

    async def on_timeout(self):
        if self.prompt_message:
            with contextlib.suppress(discord.NotFound):
                await self.prompt_message.edit(content="Response expired (no choice made).", view=None)
