"""Components v2 topic card for $topic, with optional try-another-category buttons."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

import discord
from discord import ui

from cogs.convo_starter_cog.questions import (
    CATEGORY_DESCRIPTIONS,
    CATEGORY_STYLES,
)

logger = logging.getLogger(__name__)

HINT_TIMEOUT = 180  # seconds before the category buttons grey out

type PickCategory = Callable[[discord.Interaction, str], Awaitable[None]]


class TopicCard(ui.LayoutView):
    """A bilingual question card; ``hints`` adds a row of other-category buttons."""

    def __init__(
        self,
        category: str,
        primary: str,
        translation: str,
        *,
        hints: list[str],
        on_pick: PickCategory,
    ) -> None:
        super().__init__(timeout=HINT_TIMEOUT if hints else None)
        self.message: discord.Message | None = None
        style = CATEGORY_STYLES[category]
        items: list[ui.Item] = [
            ui.TextDisplay(
                f"-# {style.emoji} {CATEGORY_DESCRIPTIONS[category]}\n"
                f"### {primary}\n{translation}"
            ),
        ]
        if hints:
            self.buttons = [_hint_button(hint, on_pick) for hint in hints]
            items += [
                ui.Separator(visible=True),
                ui.TextDisplay("-# ¿Otra categoría? / Try another category"),
                ui.ActionRow(*self.buttons),
            ]
        else:
            self.buttons = []
        self.add_item(ui.Container(*items, accent_colour=discord.Colour(style.colour)))

    async def on_timeout(self) -> None:
        """Grey out the category buttons once they expire."""
        if self.message is None:
            return
        for button in self.buttons:
            button.disabled = True
        try:
            await self.message.edit(view=self)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            logger.warning("Could not disable topic hint buttons on %s", self.message.id)


def _hint_button(category: str, on_pick: PickCategory) -> ui.Button:
    style = CATEGORY_STYLES[category]
    button: ui.Button = ui.Button(
        label=style.label, emoji=style.emoji, style=discord.ButtonStyle.secondary
    )

    async def callback(interaction: discord.Interaction) -> None:
        await on_pick(interaction, category)

    button.callback = callback
    return button
