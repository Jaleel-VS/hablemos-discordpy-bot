"""Components v2 views for the world clock: the board card and the manage panel."""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import discord

from db.world_clock import SavedClock

from . import actions, zones
from .config import MAX_CLOCKS, MAX_LABEL_LEN

if TYPE_CHECKING:
    from hablemos import Hablemos

logger = logging.getLogger(__name__)

_ACCENT = discord.Colour(0x5865F2)
_PANEL_TIMEOUT = 600
_FAILED = "Something went wrong saving your clocks. Try again in a moment."


def board_view(rendered: actions.RenderedBoard) -> discord.ui.LayoutView:
    """The board image under its title and notes."""
    text = f"## {rendered.title}" + (f"\n{rendered.body}" if rendered.body else "")
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(discord.ui.Container(
        discord.ui.TextDisplay(text),
        discord.ui.MediaGallery(discord.MediaGalleryItem(media=f"attachment://{actions.IMAGE_NAME}")),
        accent_colour=_ACCENT,
    ))
    return view


def _clock_line(clock: SavedClock, now: datetime) -> str:
    label = discord.utils.escape_markdown(clock.label)
    try:
        local = now.astimezone(zones.zone_from_key(clock.zone)).strftime("%H:%M")
    except ValueError:
        local = "unknown zone"
    return f"- **{label}**: {actions.describe_zone(clock.zone)} · {local}"


class ClockManagerView(discord.ui.LayoutView):
    """Owner-only panel listing saved clocks with add, edit and remove."""

    def __init__(
        self,
        bot: Hablemos,
        owner_id: int,
        clocks: list[SavedClock],
        selected: str | None = None,
        notice: str | None = None,
    ) -> None:
        super().__init__(timeout=_PANEL_TIMEOUT)
        self.bot = bot
        self.owner_id = owner_id
        self.clocks = clocks
        self.selected = next((c for c in clocks if c.label == selected), None)

        now = datetime.now(UTC)
        lines = [_clock_line(c, now) for c in clocks] or [
            "No clocks yet, so `$clock` shows the default cities. Press **Add** to start."
        ]
        text = f"## 🕐 Your clocks ({len(clocks)}/{MAX_CLOCKS})\n" + "\n".join(lines)
        if notice:
            text += f"\n\n{notice}"
        items: list[discord.ui.Item] = [discord.ui.TextDisplay(text)]

        if clocks:
            select = discord.ui.Select(
                placeholder="Choose a clock to edit or remove…",
                options=[
                    discord.SelectOption(
                        label=c.label, value=c.label, default=c == self.selected,
                        description=actions.describe_zone(c.zone)[:100],
                    )
                    for c in clocks
                ],
            )
            select.callback = self._pick
            self.select = select
            items.append(discord.ui.ActionRow(select))

        add = discord.ui.Button(label="Add", emoji="➕", style=discord.ButtonStyle.primary,
                                disabled=len(clocks) >= MAX_CLOCKS)
        add.callback = self._add
        edit = discord.ui.Button(label="Edit", emoji="✏️", style=discord.ButtonStyle.secondary,
                                 disabled=self.selected is None)
        edit.callback = self._edit
        remove = discord.ui.Button(label="Remove", emoji="🗑️", style=discord.ButtonStyle.danger,
                                   disabled=self.selected is None)
        remove.callback = self._remove
        items.append(discord.ui.ActionRow(add, edit, remove))
        self.add_item(discord.ui.Container(*items, accent_colour=_ACCENT))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message(
            "This panel belongs to someone else. Run `$clock list` for yours.", ephemeral=True
        )
        return False

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item) -> None:
        logger.exception("World clock panel failed for %s", interaction.user.id, exc_info=error)
        await _send_failure(interaction)

    async def refresh(
        self, interaction: discord.Interaction, *, selected: str | None = None, notice: str | None = None
    ) -> None:
        """Redraw the panel from the database in the message it lives on."""
        clocks = await self.bot.db.get_world_clocks(self.owner_id)
        view = ClockManagerView(self.bot, self.owner_id, clocks, selected, notice)
        await interaction.response.edit_message(view=view)

    async def _pick(self, interaction: discord.Interaction) -> None:
        await self.refresh(interaction, selected=self.select.values[0])

    async def _add(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(ClockModal(self, None))

    async def _edit(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(ClockModal(self, self.selected))

    async def _remove(self, interaction: discord.Interaction) -> None:
        if self.selected is None:
            await self.refresh(interaction)
            return
        removed = await self.bot.db.remove_world_clock(self.owner_id, self.selected.label)
        label = discord.utils.escape_markdown(self.selected.label)
        await self.refresh(interaction, notice=f"Removed **{label}**." if removed else None)


class ClockModal(discord.ui.Modal):
    """Name and timezone form for adding or editing one clock."""

    def __init__(self, panel: ClockManagerView, editing: SavedClock | None) -> None:
        super().__init__(title="Edit clock" if editing else "Add a clock", timeout=_PANEL_TIMEOUT)
        self.panel = panel
        self.editing = editing
        self.name = discord.ui.TextInput(
            label="Name", placeholder="Emily", max_length=MAX_LABEL_LEN,
            default=editing.label if editing else None,
        )
        self.zone = discord.ui.TextInput(
            label="Timezone", placeholder="Berlin, America/Bogota or UTC+2", max_length=64,
            default=editing.zone if editing else None,
        )
        self.add_item(self.name)
        self.add_item(self.zone)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        db = self.panel.bot.db
        owner = self.panel.owner_id
        if self.editing is None:
            outcome = await actions.add_clock(db, owner, self.name.value, self.zone.value)
        else:
            outcome = await actions.edit_clock(db, owner, self.editing.label, self.name.value, self.zone.value)
        if not outcome.ok:
            await interaction.response.send_message(outcome.message, ephemeral=True)
            return
        await self.panel.refresh(interaction, notice=outcome.message)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        logger.exception("World clock form failed for %s", interaction.user.id, exc_info=error)
        await _send_failure(interaction)


async def _send_failure(interaction: discord.Interaction) -> None:
    try:
        if interaction.response.is_done():
            await interaction.followup.send(_FAILED, ephemeral=True)
        else:
            await interaction.response.send_message(_FAILED, ephemeral=True)
    except discord.HTTPException:
        logger.warning("Could not report world clock failure to %s", interaction.user.id)
