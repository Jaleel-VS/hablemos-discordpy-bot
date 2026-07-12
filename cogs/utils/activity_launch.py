"""Shared launcher for the embedded Discord Activity.

Discord Activities normally open from the 🚀 Activity Shelf, which is hard to
find. A command posts a message with a button that launches the Activity
directly via the ``LAUNCH_ACTIVITY`` interaction response (discord.py 2.6+
``interaction.response.launch_activity()``, callback type 12).

Discord opens the Activity in the channel the button was clicked from — servers
and DMs are both valid contexts, so no voice channel is required.

There is **one** Activity (one app / one ``client_id``), so every launcher
button opens the same app. The app decides what to show: with a single game
registered it boots straight into that game; with several it shows the game
hub/menu. The ``LAUNCH_ACTIVITY`` callback carries no deep-link parameter, so a
per-game command (``$wordle`` vs ``$conjuga``) cannot pre-select a game — it is
a themed, discoverable entry point that lands on the hub. This is intentional
and centralized here so both launcher cogs share identical behavior.
"""
from __future__ import annotations

import logging

import discord

logger = logging.getLogger(__name__)

# How long the posted button stays clickable before Discord drops the
# interaction. Short since it's an on-demand, click-right-away button.
VIEW_TIMEOUT = 180

# User-facing failure message (never leaks the underlying exception).
_LAUNCH_ERROR = "No pude abrir el juego. Inténtalo de nuevo en un momento."


class ActivityLaunchView(discord.ui.View):
    """A one-button view that launches the app's Activity when clicked.

    ``label`` and ``emoji`` are configurable so each game's launcher can theme
    its button, but the launch behavior is identical (open the one Activity).
    """

    def __init__(self, *, label: str, emoji: str) -> None:
        super().__init__(timeout=VIEW_TIMEOUT)
        # Build the button dynamically so label/emoji can vary per launcher.
        button: discord.ui.Button = discord.ui.Button(
            label=label, emoji=emoji, style=discord.ButtonStyle.primary,
        )
        button.callback = self._launch
        self.add_item(button)

    async def _launch(self, interaction: discord.Interaction) -> None:
        try:
            # Launches the app's Activity in the channel this button was
            # clicked from. No message payload needed.
            await interaction.response.launch_activity()
        except discord.HTTPException as exc:
            logger.warning("launch_activity failed for user %s: %s", interaction.user.id, exc)
            if interaction.response.is_done():
                await interaction.followup.send(_LAUNCH_ERROR, ephemeral=True)
            else:
                await interaction.response.send_message(_LAUNCH_ERROR, ephemeral=True)
