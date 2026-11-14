"""Components v2 views for the world clock: the board card, the private menu
and its launcher.

``/clock menu`` opens :class:`ClockMenuView` ephemerally. ``$clock menu``
can't reply privately, so it posts :class:`ClockMenuLauncherView`, a single
button that opens the clicker's own ephemeral menu (the ``$myclock`` pattern).
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
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
_FAILED = "Something went wrong with your clocks. Try again in a moment."


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


def _button(label: str, emoji: str, style: discord.ButtonStyle, callback, *, disabled: bool = False) -> discord.ui.Button:
    button = discord.ui.Button(label=label, emoji=emoji, style=style, disabled=disabled)
    button.callback = callback
    return button


async def open_menu(bot: Hablemos, interaction: discord.Interaction) -> None:
    """Reply to *interaction* with the clicker's private menu."""
    clocks = await bot.db.get_world_clocks(interaction.user.id)
    await interaction.response.send_message(
        view=ClockMenuView(bot, interaction.user.id, clocks), ephemeral=True
    )


class ClockMenuView(discord.ui.LayoutView):
    """A member's private menu: list, add, edit, remove, preview, post, reset."""

    def __init__(
        self,
        bot: Hablemos,
        owner_id: int,
        clocks: list[SavedClock],
        selected: str | None = None,
        notice: str | None = None,
        confirming_reset: bool = False,
    ) -> None:
        super().__init__(timeout=_PANEL_TIMEOUT)
        self.bot = bot
        self.owner_id = owner_id
        self.selected = next((c for c in clocks if c.label == selected), None)

        now = datetime.now(UTC)
        lines = [_clock_line(c, now) for c in clocks] or [
            "No clocks yet, so your board shows the default cities. Press **Add** to start."
        ]
        text = f"## 🕐 Your clocks ({len(clocks)}/{MAX_CLOCKS})\n" + "\n".join(lines)
        if notice:
            text += f"\n\n{notice}"
        items: list[discord.ui.Item] = [discord.ui.TextDisplay(text)]

        if confirming_reset:
            items.append(discord.ui.TextDisplay(f"**Delete all {len(clocks)} clocks?** This can't be undone."))
            items.append(discord.ui.ActionRow(
                _button("Yes, delete all", "🗑️", discord.ButtonStyle.danger, self._reset_confirmed),
                _button("Cancel", "↩️", discord.ButtonStyle.secondary, self._reset_cancelled),
            ))
            self.add_item(discord.ui.Container(*items, accent_colour=_ACCENT))
            return

        if clocks:
            self.select = discord.ui.Select(
                placeholder="Choose a clock to edit or remove…",
                options=[
                    discord.SelectOption(
                        label=c.label, value=c.label, default=c == self.selected,
                        description=actions.describe_zone(c.zone)[:100],
                    )
                    for c in clocks
                ],
            )
            self.select.callback = self._pick
            items.append(discord.ui.ActionRow(self.select))

        nothing_selected = self.selected is None
        items.append(discord.ui.ActionRow(
            _button("Add", "➕", discord.ButtonStyle.primary, self._add, disabled=len(clocks) >= MAX_CLOCKS),
            _button("Edit", "✏️", discord.ButtonStyle.secondary, self._edit, disabled=nothing_selected),
            _button("Remove", "➖", discord.ButtonStyle.secondary, self._remove, disabled=nothing_selected),
        ))
        items.append(discord.ui.ActionRow(
            _button("Preview", "👀", discord.ButtonStyle.secondary, self._preview),
            _button("Post to channel", "📤", discord.ButtonStyle.secondary, self._post),
            _button("Reset all", "🗑️", discord.ButtonStyle.danger, self._reset, disabled=not clocks),
        ))
        self.add_item(discord.ui.Container(*items, accent_colour=_ACCENT))

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item) -> None:
        logger.exception("World clock menu failed for %s", interaction.user.id, exc_info=error)
        await _send_failure(interaction)

    async def refresh(
        self,
        interaction: discord.Interaction,
        *,
        selected: str | None = None,
        notice: str | None = None,
        confirming_reset: bool = False,
    ) -> None:
        """Redraw the menu from the database in the message it lives on."""
        clocks = await self.bot.db.get_world_clocks(self.owner_id)
        view = ClockMenuView(self.bot, self.owner_id, clocks, selected, notice, confirming_reset)
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

    async def _preview(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        rendered = await actions.render_board(self.bot.db, self.owner_id, None)
        await interaction.followup.send(view=board_view(rendered), file=rendered.file(), ephemeral=True)

    async def _post(self, interaction: discord.Interaction) -> None:
        channel = interaction.channel
        if not isinstance(channel, discord.abc.Messageable):
            await interaction.response.send_message("I can't post in this channel.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        rendered = await actions.render_board(self.bot.db, self.owner_id, None)
        try:
            await channel.send(view=board_view(rendered), file=rendered.file())
        except discord.Forbidden:
            await interaction.followup.send("I'm not allowed to post in this channel.", ephemeral=True)
            return
        await interaction.followup.send("📤 Posted your board.", ephemeral=True)

    async def _reset(self, interaction: discord.Interaction) -> None:
        await self.refresh(interaction, confirming_reset=True)

    async def _reset_confirmed(self, interaction: discord.Interaction) -> None:
        removed = await self.bot.db.clear_world_clocks(self.owner_id)
        await self.refresh(interaction, notice=f"Removed {removed} clock(s).")

    async def _reset_cancelled(self, interaction: discord.Interaction) -> None:
        await self.refresh(interaction)


class ClockMenuLauncherView(discord.ui.LayoutView):
    """Public button that opens each clicker's private menu.

    When ``owner_id`` (who ran ``$clock menu``) clicks, the launcher deletes
    itself. The startup-registered persistent instance has no owner, so
    launchers that outlive a restart stay for anyone to use.
    """

    def __init__(self, bot: Hablemos, owner_id: int | None = None) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.owner_id = owner_id
        button = discord.ui.Button(
            label="Manage my clocks", emoji="🕐", style=discord.ButtonStyle.primary,
            custom_id="world_clock:menu",
        )
        button.callback = self.launch
        self.add_item(discord.ui.Container(
            discord.ui.TextDisplay(
                "## 🌍 World clock\n"
                "Add, edit and preview your clocks. Only you will see your menu."
            ),
            discord.ui.ActionRow(button),
            accent_colour=_ACCENT,
        ))

    async def launch(self, interaction: discord.Interaction) -> None:
        try:
            await open_menu(self.bot, interaction)
        except Exception:
            logger.exception("Failed to open world clock menu for %s", interaction.user.id)
            await _send_failure(interaction)
        if interaction.user.id == self.owner_id and interaction.message is not None:
            try:
                await interaction.message.delete()
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                logger.warning("Could not delete world clock launcher %s", interaction.message.id)


_OFFSET_HOURS = range(-11, 14)  # 25 options, Discord's limit for one dropdown


def _offset_options(now: datetime, selected: str | None) -> list[discord.SelectOption]:
    """One option per whole-hour offset; the description shows its time right now."""
    options = []
    for hours in _OFFSET_HOURS:
        offset = timedelta(hours=hours)
        key = zones.resolve_zone(zones.format_offset(offset)) or "UTC+00:00"
        options.append(discord.SelectOption(
            label=zones.format_offset(offset),
            value=key,
            description=f"Now {now + offset:%H:%M}",
            default=key == selected,
        ))
    return options


def chosen_zone(picked: list[str], typed: str, prefilled: str | None) -> str:
    """The zone the member meant: newly typed text, else the dropdown, else the
    prefilled text left as it was ("" when nothing was given)."""
    typed = typed.strip()
    if typed and typed != (prefilled or ""):
        return typed
    return picked[0] if picked else typed


class ClockModal(discord.ui.Modal):
    """Name, a UTC-offset dropdown, and an optional typed timezone for anything else."""

    def __init__(self, menu: ClockMenuView, editing: SavedClock | None) -> None:
        super().__init__(title="Edit clock" if editing else "Add a clock", timeout=_PANEL_TIMEOUT)
        self.menu = menu
        self.editing = editing
        options = _offset_options(datetime.now(UTC), editing.zone if editing else None)
        in_list = editing is not None and any(o.default for o in options)
        self.name_input = discord.ui.TextInput(
            placeholder="Emily", max_length=MAX_LABEL_LEN,
            default=editing.label if editing else None,
        )
        self.offset_select = discord.ui.Select(
            placeholder="Pick the offset whose time matches theirs", options=options,
            required=False, min_values=0,
        )
        self.other_input = discord.ui.TextInput(
            placeholder="UTC+5:30, Delhi or Europe/Berlin", max_length=64, required=False,
            default=editing.zone if editing and not in_list else None,
        )
        self.add_item(discord.ui.Label(text="Name", component=self.name_input))
        self.add_item(discord.ui.Label(
            text="Timezone", description="Fixed offset: change it yourself when daylight saving starts or ends.",
            component=self.offset_select,
        ))
        self.add_item(discord.ui.Label(
            text="Not in the list?", description="Type an offset or a place. A place follows daylight saving.",
            component=self.other_input,
        ))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        db = self.menu.bot.db
        owner = self.menu.owner_id
        zone = chosen_zone(self.offset_select.values, self.other_input.value, self.other_input.default)
        if not zone:
            await interaction.response.send_message("Pick a timezone from the list or type one.", ephemeral=True)
            return
        name = self.name_input.value
        if self.editing is None:
            outcome = await actions.add_clock(db, owner, name, zone)
        else:
            outcome = await actions.edit_clock(db, owner, self.editing.label, name, zone)
        if not outcome.ok:
            await interaction.response.send_message(outcome.message, ephemeral=True)
            return
        await self.menu.refresh(interaction, notice=outcome.message)

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
