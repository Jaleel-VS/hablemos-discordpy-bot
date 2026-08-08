"""Interactive views for the $myclock activity clock.

Flow (all per-user and ephemeral after the first click):

1. ``$myclock`` posts a public message carrying :class:`ClockLauncherView` — a
   single button. Anyone may click it; each clicker gets their own ephemeral
   result, so one posted message serves the whole channel.
2. On click we look up the clicker's saved UTC offset.
   - Saved  → render their clock straight away, with a "change timezone" button.
   - Unset  → show :class:`TimezonePickerView`, a dropdown of whole-hour UTC
     offsets. Each option's description shows the wall-clock time that offset
     implies *right now*, and the prompt embeds ``<t:now:t>`` so Discord renders
     the clicker's own local time as the reference to match against.
3. Picking an offset persists it (so the picker is a one-time step) and renders.

Whole-hour offsets keep the hour-of-day chart exactly aligned to the UTC hour
buckets the data is stored in, so no timezone database is needed.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import discord

from cogs.utils.embeds import red_embed

from . import clock

if TYPE_CHECKING:
    from hablemos import Hablemos

logger = logging.getLogger(__name__)

VIEW_TIMEOUT = 180
_CLOCK_DAYS = 30  # rolling window the clock summarizes

# Whole-hour offsets offered in the picker. Kept to the populated range of real
# world offsets (UTC-11 … UTC+13) to fit Discord's 25-option select limit.
_OFFSETS = list(range(-11, 14))

_LAUNCH_ERROR = "No pude generar tu reloj. Inténtalo de nuevo en un momento."
_NO_DATA = (
    "Todavía no tienes actividad registrada en los últimos {days} días, "
    "así que no hay reloj que mostrar. ¡Escribe un poco y vuelve luego!"
)


def _format_offset(offset: int) -> str:
    """Human label for a whole-hour UTC offset, e.g. ``UTC+1`` / ``UTC−5``."""
    sign = "+" if offset >= 0 else "−"
    return f"UTC{sign}{abs(offset)}"


def _now_at_offset(offset: int) -> str:
    """Current wall-clock time (``HH:MM``) at a whole-hour UTC offset."""
    return (datetime.now(UTC) + timedelta(hours=offset)).strftime("%H:%M")


async def _render_clock_file(
    bot: Hablemos, user_id: int, offset: int
) -> discord.File | None:
    """Fetch a user's hourly distribution and render it, or None if no data."""
    hours = await bot.db.get_user_hourly_distribution(user_id, _CLOCK_DAYS, offset)
    if sum(hours) == 0:
        return None
    buf = await asyncio.to_thread(clock.render_activity_clock, hours, offset)
    return discord.File(buf, filename="activity_clock.png")


async def _send_clock(interaction: discord.Interaction, bot: Hablemos, offset: int) -> None:
    """Render and deliver the clock as an ephemeral followup (response deferred)."""
    file = await _render_clock_file(bot, interaction.user.id, offset)
    if file is None:
        await interaction.followup.send(
            embed=red_embed(_NO_DATA.format(days=_CLOCK_DAYS)),
            ephemeral=True,
        )
        return

    embed = discord.Embed(
        title="🕐 Tu reloj de actividad",
        description=(
            f"Cuándo escribes, en los últimos **{_CLOCK_DAYS} días** "
            f"({_format_offset(offset)}).\n"
            "Los pétalos largos y oscuros son tus horas más activas."
        ),
        color=0x5865F2,
    )
    embed.set_image(url="attachment://activity_clock.png")
    await interaction.followup.send(
        embed=embed,
        file=file,
        view=ChangeTimezoneView(bot),
        ephemeral=True,
    )


class ClockLauncherView(discord.ui.View):
    """Public one-button launcher. Each clicker gets their own ephemeral clock."""

    def __init__(self, bot: Hablemos) -> None:
        super().__init__(timeout=None)  # persistent-friendly; button is idempotent
        self.bot = bot

    @discord.ui.button(
        label="Ver mi reloj", emoji="🕐", style=discord.ButtonStyle.primary,
        custom_id="stats_clock:launch",
    )
    async def launch(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            offset = await self.bot.db.get_user_clock_tz(interaction.user.id)
            if offset is None:
                await interaction.followup.send(
                    embed=_picker_prompt(),
                    view=TimezonePickerView(self.bot),
                    ephemeral=True,
                )
                return
            await _send_clock(interaction, self.bot, offset)
        except Exception:
            logger.exception("Failed to build activity clock for %s", interaction.user.id)
            await interaction.followup.send(embed=red_embed(_LAUNCH_ERROR), ephemeral=True)


def _picker_prompt() -> discord.Embed:
    """The 'confirm your timezone' embed, anchored to the viewer's local time."""
    now_ts = int(datetime.now(UTC).timestamp())
    return discord.Embed(
        title="🌍 ¿Cuál es tu zona horaria?",
        description=(
            f"Tu hora local ahora mismo es <t:{now_ts}:t>.\n"
            "Elige la opción de abajo cuya hora coincida — la usaré para "
            "etiquetar tu reloj y la recordaré la próxima vez."
        ),
        color=0x5865F2,
    )


class TimezonePickerView(discord.ui.View):
    """Ephemeral dropdown to pick (and persist) a whole-hour UTC offset."""

    def __init__(self, bot: Hablemos) -> None:
        super().__init__(timeout=VIEW_TIMEOUT)
        self.bot = bot
        self.add_item(_TimezoneSelect())


class _TimezoneSelect(discord.ui.Select):
    """Select whose option descriptions show the current time at each offset."""

    def __init__(self) -> None:
        options = [
            discord.SelectOption(
                label=_format_offset(off),
                value=str(off),
                description=f"Ahora serían las {_now_at_offset(off)}",
            )
            for off in _OFFSETS
        ]
        super().__init__(placeholder="Elige tu zona horaria…", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: TimezonePickerView = self.view  # type: ignore[assignment]
        offset = int(self.values[0])
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            await view.bot.db.set_user_clock_tz(interaction.user.id, offset)
            await _send_clock(interaction, view.bot, offset)
        except Exception:
            logger.exception("Failed to save/render clock tz for %s", interaction.user.id)
            await interaction.followup.send(embed=red_embed(_LAUNCH_ERROR), ephemeral=True)


class ChangeTimezoneView(discord.ui.View):
    """Attached under a rendered clock: lets the user re-pick their timezone."""

    def __init__(self, bot: Hablemos) -> None:
        super().__init__(timeout=VIEW_TIMEOUT)
        self.bot = bot

    @discord.ui.button(
        label="Cambiar zona horaria", emoji="🌍", style=discord.ButtonStyle.secondary
    )
    async def change(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.send_message(
            embed=_picker_prompt(),
            view=TimezonePickerView(self.bot),
            ephemeral=True,
        )
