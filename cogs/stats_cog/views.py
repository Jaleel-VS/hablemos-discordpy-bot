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


_ACCENT = discord.Colour(0x5865F2)
_CLOCK_IMAGE = "attachment://activity_clock.png"


def _clock_card(title: str, body: str, *extra: discord.ui.Item) -> discord.ui.Container:
    """Container holding a heading, a body, the clock image, then *extra* items."""
    return discord.ui.Container(
        discord.ui.TextDisplay(f"## {title}\n{body}"),
        discord.ui.MediaGallery(discord.MediaGalleryItem(media=_CLOCK_IMAGE)),
        *extra,
        accent_colour=_ACCENT,
    )


async def _send_clock(interaction: discord.Interaction, bot: Hablemos, offset: int) -> None:
    """Render and deliver the clock as an ephemeral followup (response deferred)."""
    file = await _render_clock_file(bot, interaction.user.id, offset)
    if file is None:
        await interaction.followup.send(
            embed=red_embed(_NO_DATA.format(days=_CLOCK_DAYS)),
            ephemeral=True,
        )
        return
    await interaction.followup.send(
        file=file, view=ClockResultView(bot, offset), ephemeral=True
    )


def _public_clock_view(user: discord.abc.User, offset: int) -> discord.ui.LayoutView:
    """Clock card shared publicly — attributed to its owner, no controls."""
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(_clock_card(
        f"🕐 El reloj de actividad de {user.display_name}",
        f"Cuándo escribe, en los últimos **{_CLOCK_DAYS} días** ({_format_offset(offset)}).",
    ))
    return view


class ClockLauncherView(discord.ui.LayoutView):
    """Public one-button launcher. Each clicker gets their own ephemeral clock.

    When ``owner_id`` (the user who ran ``$myclock``) clicks, the launcher is
    deleted once their result is delivered. The startup-registered persistent
    instance has no owner, so launchers that outlive a restart are never deleted.
    """

    def __init__(self, bot: Hablemos, owner_id: int | None = None) -> None:
        super().__init__(timeout=None)  # persistent-friendly; button is idempotent
        self.bot = bot
        self.owner_id = owner_id
        button = discord.ui.Button(
            label="Ver mi reloj", emoji="🕐", style=discord.ButtonStyle.primary,
            custom_id="stats_clock:launch",
        )
        button.callback = self.launch
        self.add_item(discord.ui.Container(
            discord.ui.TextDisplay(
                "## 🕐 Tu reloj de actividad\n"
                "Descubre a qué horas del día sueles escribir más.\n\n"
                "Pulsa el botón para ver tu reloj (solo tú lo verás)."
            ),
            discord.ui.ActionRow(button),
            accent_colour=_ACCENT,
        ))

    async def launch(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            offset = await self.bot.db.get_user_clock_tz(interaction.user.id)
            if offset is None:
                await interaction.followup.send(
                    view=TimezonePickerView(self.bot), ephemeral=True
                )
            else:
                await _send_clock(interaction, self.bot, offset)
        except Exception:
            logger.exception("Failed to build activity clock for %s", interaction.user.id)
            await interaction.followup.send(embed=red_embed(_LAUNCH_ERROR), ephemeral=True)
        if interaction.user.id == self.owner_id and interaction.message is not None:
            try:
                await interaction.message.delete()
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                logger.warning("Could not delete clock launcher %s", interaction.message.id)


class TimezonePickerView(discord.ui.LayoutView):
    """Ephemeral prompt + dropdown to pick (and persist) a whole-hour UTC offset.

    The prompt embeds ``<t:now:t>`` so it is anchored to the viewer's local time.
    """

    def __init__(self, bot: Hablemos) -> None:
        super().__init__(timeout=VIEW_TIMEOUT)
        self.bot = bot
        select = discord.ui.Select(
            placeholder="Elige tu zona horaria…",
            options=[
                discord.SelectOption(
                    label=_format_offset(off),
                    value=str(off),
                    description=f"Ahora serían las {_now_at_offset(off)}",
                )
                for off in _OFFSETS
            ],
        )
        select.callback = self.pick
        self.select = select
        now_ts = int(datetime.now(UTC).timestamp())
        self.add_item(discord.ui.Container(
            discord.ui.TextDisplay(
                "## 🌍 ¿Cuál es tu zona horaria?\n"
                f"Tu hora local ahora mismo es <t:{now_ts}:t>.\n"
                "Elige la opción de abajo cuya hora coincida — la usaré para "
                "etiquetar tu reloj y la recordaré la próxima vez."
            ),
            discord.ui.ActionRow(select),
            accent_colour=_ACCENT,
        ))

    async def pick(self, interaction: discord.Interaction) -> None:
        offset = int(self.select.values[0])
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            await self.bot.db.set_user_clock_tz(interaction.user.id, offset)
            await _send_clock(interaction, self.bot, offset)
        except Exception:
            logger.exception("Failed to save/render clock tz for %s", interaction.user.id)
            await interaction.followup.send(embed=red_embed(_LAUNCH_ERROR), ephemeral=True)


class ClockResultView(discord.ui.LayoutView):
    """A user's ephemeral clock card with its two actions.

    Share the clock to the current channel, or re-pick the timezone. The offset
    is carried so "post" can re-render (a rendered ``discord.File`` is
    single-use and cannot be re-sent from the ephemeral one).
    """

    def __init__(self, bot: Hablemos, offset: int) -> None:
        super().__init__(timeout=VIEW_TIMEOUT)
        self.bot = bot
        self.offset = offset
        self.post_button = discord.ui.Button(
            label="Publicar en el canal", emoji="📤", style=discord.ButtonStyle.primary
        )
        self.post_button.callback = self.post
        change_button = discord.ui.Button(
            label="Cambiar zona horaria", emoji="🌍", style=discord.ButtonStyle.secondary
        )
        change_button.callback = self.change
        self.add_item(_clock_card(
            "🕐 Tu reloj de actividad",
            f"Cuándo escribes, en los últimos **{_CLOCK_DAYS} días** "
            f"({_format_offset(offset)}).\n"
            "Los pétalos largos y oscuros son tus horas más activas.",
            discord.ui.ActionRow(self.post_button, change_button),
        ))

    async def post(self, interaction: discord.Interaction) -> None:
        channel = interaction.channel
        if not isinstance(channel, discord.abc.Messageable):
            await interaction.response.send_message(
                embed=red_embed("No puedo publicar aquí."), ephemeral=True
            )
            return

        await interaction.response.defer()
        try:
            file = await _render_clock_file(self.bot, interaction.user.id, self.offset)
            if file is None:
                await interaction.followup.send(
                    embed=red_embed(_NO_DATA.format(days=_CLOCK_DAYS)), ephemeral=True
                )
                return
            await channel.send(
                view=_public_clock_view(interaction.user, self.offset), file=file
            )
        except Exception:
            logger.exception("Failed to post clock for %s", interaction.user.id)
            await interaction.followup.send(embed=red_embed(_LAUNCH_ERROR), ephemeral=True)
            return

        self.post_button.disabled = True
        await interaction.edit_original_response(view=self)

    async def change(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            view=TimezonePickerView(self.bot), ephemeral=True
        )
