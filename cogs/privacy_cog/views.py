"""Confirmation view for deleting a user's stored data."""
from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING

import discord
from discord import ButtonStyle, Interaction, ui

from cogs.utils.embeds import green_embed, red_embed, yellow_embed
from db.privacy import KEPT_TABLES

if TYPE_CHECKING:
    from hablemos import Hablemos

logger = logging.getLogger(__name__)

CONFIRM_TIMEOUT_SECONDS = 60


def confirm_embed(subject: str) -> discord.Embed:
    """Explain what deletion removes and keeps, before the user confirms."""
    kept = ", ".join(sorted(set(KEPT_TABLES.values())))
    return yellow_embed(
        f"This permanently deletes everything the bot stores about {subject}: "
        "notes, vocab notes, League standings, game scores, dictation answers, "
        "message counts, interaction records, settings and command history.\n\n"
        f"**Kept:** {kept}.\n\n"
        "This can't be undone."
    )


class ConfirmDeleteDataView(ui.View):
    """Delete ``target_id``'s data once ``requester_id`` confirms."""

    def __init__(
        self, bot: Hablemos, requester_id: int, target_id: int, confirm_label: str = "Delete my data",
    ) -> None:
        super().__init__(timeout=CONFIRM_TIMEOUT_SECONDS)
        self.confirm.label = confirm_label
        self.bot = bot
        self.requester_id = requester_id
        self.target_id = target_id
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message("This menu isn't yours.", ephemeral=True)
            return False
        return True

    def _disable(self) -> None:
        for item in self.children:
            if isinstance(item, ui.Button):
                item.disabled = True

    @ui.button(label="Delete my data", style=ButtonStyle.danger)
    async def confirm(self, interaction: Interaction, _button: ui.Button) -> None:
        self._disable()
        self.stop()
        try:
            rows = await self.bot.db.delete_user_data(self.target_id)
        except Exception:
            logger.exception("User data deletion failed")
            await interaction.response.edit_message(
                embed=red_embed("Something went wrong and nothing was deleted. Please try again later."),
                view=self,
            )
            return
        self.bot.dispatch("user_data_deleted", self.target_id)
        await interaction.response.edit_message(
            embed=green_embed(f"Done. Deleted {rows} stored records."),
            view=self,
        )

    @ui.button(label="Cancel", style=ButtonStyle.secondary)
    async def cancel(self, interaction: Interaction, _button: ui.Button) -> None:
        self._disable()
        self.stop()
        await interaction.response.edit_message(
            embed=green_embed("Cancelled. Nothing was deleted."), view=self,
        )

    async def on_timeout(self) -> None:
        self._disable()
        if self.message is not None:
            with contextlib.suppress(discord.HTTPException):
                await self.message.edit(view=self)
