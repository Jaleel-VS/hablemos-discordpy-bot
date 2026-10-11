"""One-time opt-in prompt for Spotify sharing."""
from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING

import discord
from discord import ButtonStyle, Interaction, ui
from discord.ext import commands

from cogs.utils.embeds import green_embed, red_embed, yellow_embed

if TYPE_CHECKING:
    from hablemos import Hablemos

logger = logging.getLogger(__name__)

PROMPT_TIMEOUT_SECONDS = 60


def prompt_embed() -> discord.Embed:
    """Ask for consent, and say who can see the result."""
    return yellow_embed(
        "Spotify sharing is **off** for you, so the bot can't show what you're listening to.\n\n"
        "If you turn it on, anyone in the server can see your current track with "
        "`$np @you`. You can turn it off any time with `$spotify off`."
    )


class OptInView(ui.View):
    """Lets the member who ran the command turn sharing on, then re-runs the command.

    Only the requester can press the button, and only for themselves. A member
    cannot opt in someone else, so lookups of other members never show it.
    """

    def __init__(self, bot: Hablemos, ctx: commands.Context) -> None:
        super().__init__(timeout=PROMPT_TIMEOUT_SECONDS)
        self.bot = bot
        self.ctx = ctx
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This button isn't yours.", ephemeral=True)
            return False
        return True

    def _disable(self) -> None:
        for item in self.children:
            if isinstance(item, ui.Button):
                item.disabled = True

    @ui.button(label="Turn on Spotify sharing", style=ButtonStyle.success)
    async def opt_in(self, interaction: Interaction, _button: ui.Button) -> None:
        try:
            await self.bot.db.spotify_optin(self.ctx.author.id)
        except Exception:
            logger.exception("Spotify opt-in failed")
            await interaction.response.send_message(
                embed=red_embed("Something went wrong. Please try again later."), ephemeral=True,
            )
            return

        self.stop()
        self._disable()
        await interaction.response.edit_message(
            embed=green_embed(
                "Spotify sharing is now **on**. Turn it off any time with `$spotify off`."
            ),
            view=self,
        )
        # Re-run the original command. reinvoke skips checks and cooldowns.
        try:
            await self.ctx.reinvoke()
        except Exception:
            logger.exception("Spotify card failed after opt-in")
            await interaction.followup.send(
                embed=red_embed("Sharing is on, but I couldn't show the card. Please run the command again."),
                ephemeral=True,
            )

    async def on_timeout(self) -> None:
        self._disable()
        if self.message is not None:
            with contextlib.suppress(discord.HTTPException):
                await self.message.edit(view=self)
