"""Interactive opt-in/opt-out UI for the quote generator cog.

``QuoteOptView`` backs the ``$q0`` command: an ephemeral message with two
buttons — **Opt in** and **Opt out** — that toggle the invoker's quote
opt-out status. The button matching the current status is disabled so the
active state is obvious, and clicking re-renders both the embed and the
buttons to reflect the new status.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import Interaction

from cogs.utils.embeds import green_embed, yellow_embed

if TYPE_CHECKING:
    from hablemos import Hablemos

logger = logging.getLogger(__name__)

VIEW_TIMEOUT = 120  # seconds


def _status_embed(opted_out: bool) -> discord.Embed:
    """Build the status embed reflecting the current opt-out state."""
    if opted_out:
        return yellow_embed(
            "You are currently **opted out** of being quoted. "
            "Others cannot quote your messages (you can still quote yourself)."
        )
    return green_embed(
        "You are currently **opted in** to being quoted. "
        "Others can quote your messages."
    )


class QuoteOptView(discord.ui.View):
    """Ephemeral, per-invoker view with Opt in / Opt out buttons."""

    def __init__(self, bot: Hablemos, user_id: int, opted_out: bool):
        super().__init__(timeout=VIEW_TIMEOUT)
        self.bot = bot
        self.user_id = user_id
        self._sync_buttons(opted_out)

    def _sync_buttons(self, opted_out: bool) -> None:
        """Disable the button matching the current status."""
        self.opt_in_button.disabled = not opted_out
        self.opt_out_button.disabled = opted_out

    async def interaction_check(self, interaction: Interaction) -> bool:
        """Only the invoker may use the buttons."""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This isn't your quote-status panel. Use `$q0` to open your own.",
                ephemeral=True,
            )
            return False
        return True

    async def _apply(self, interaction: Interaction, *, opted_out: bool) -> None:
        """Persist the new status, then re-render the embed and buttons."""
        if opted_out:
            await self.bot.db.quote_optout(self.user_id)
        else:
            await self.bot.db.quote_optin(self.user_id)
        self._sync_buttons(opted_out)
        await interaction.response.edit_message(
            embed=_status_embed(opted_out), view=self,
        )

    @discord.ui.button(label="Opt in", style=discord.ButtonStyle.success, emoji="✅")
    async def opt_in_button(self, interaction: Interaction, _button: discord.ui.Button):
        await self._apply(interaction, opted_out=False)

    @discord.ui.button(label="Opt out", style=discord.ButtonStyle.danger, emoji="🚫")
    async def opt_out_button(self, interaction: Interaction, _button: discord.ui.Button):
        await self._apply(interaction, opted_out=True)
