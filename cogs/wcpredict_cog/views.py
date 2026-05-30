"""Views for the World Cup predictions cog.

Mirrors the structure of `cogs/worldcup_cog/views.py` (paginated team
picker with menu) but persists the user's pick to the database instead
of granting a Discord role.
"""
import logging

import discord
from discord import ButtonStyle, Interaction
from discord.ui import Button, Select, View

from .config import WC_PREDICT_LOG_CHANNEL_ID

logger = logging.getLogger(__name__)

TEAMS_PER_PAGE = 24


class WCPredictMenuView(View):
    """Top-level menu — pick / change / clear a prediction."""

    def __init__(
        self,
        teams: list[discord.Role],
        user_id: int,
        bot,
        current_pick: discord.Role | None = None,
        timeout: float = 180,
    ):
        super().__init__(timeout=timeout)
        self.teams = teams
        self.user_id = user_id
        self.bot = bot
        self.current_pick = current_pick

        pick_label = "Change my pick" if current_pick is not None else "Pick a winner"
        pick_btn = Button(label=pick_label, style=ButtonStyle.primary)
        pick_btn.callback = self._pick
        self.add_item(pick_btn)

        if current_pick is not None:
            clear_btn = Button(
                label=f"Clear ({current_pick.name})",
                style=ButtonStyle.danger,
            )
            clear_btn.callback = self._clear
            self.add_item(clear_btn)

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This menu isn't yours.", ephemeral=True)
            return False
        return True

    async def _pick(self, interaction: Interaction) -> None:
        view = WCPredictTeamSelectView(
            teams=self.teams,
            user_id=self.user_id,
            bot=self.bot,
            current_pick=self.current_pick,
        )
        await interaction.response.edit_message(
            content="Pick the team you think will win the World Cup:",
            view=view,
        )

    async def _clear(self, interaction: Interaction) -> None:
        role = self.current_pick
        try:
            await self.bot.db.delete_wc_prediction(self.user_id)
        except Exception as exc:
            logger.error("Failed to delete prediction for %s: %s", self.user_id, exc)
            await interaction.response.edit_message(
                content="Something went wrong clearing your prediction. Please try again.",
                view=None,
            )
            return

        await interaction.response.edit_message(
            content=f"Cleared your prediction (**{role.name}**).", view=None,
        )
        self.stop()
        await _log_clear(interaction, role)

    async def on_timeout(self) -> None:
        logger.debug("WCPredictMenuView timed out for user %s", self.user_id)


class WCPredictTeamSelectView(View):
    """Paginated team picker that writes the prediction to the DB."""

    def __init__(
        self,
        teams: list[discord.Role],
        user_id: int,
        bot,
        current_pick: discord.Role | None = None,
        page: int = 0,
        timeout: float = 180,
    ):
        super().__init__(timeout=timeout)
        self.teams = teams
        self.user_id = user_id
        self.bot = bot
        self.current_pick = current_pick
        self.page = page
        self.total_pages = max(1, (len(teams) - 1) // TEAMS_PER_PAGE + 1)
        self._rebuild()

    def _rebuild(self) -> None:
        self.clear_items()
        start = self.page * TEAMS_PER_PAGE
        page_teams = self.teams[start : start + TEAMS_PER_PAGE]

        options = [
            discord.SelectOption(
                label=role.name,
                value=str(role.id),
                default=self.current_pick is not None and role.id == self.current_pick.id,
            )
            for role in page_teams
        ]
        select = Select(
            placeholder=f"Choose a team... (page {self.page + 1}/{self.total_pages})",
            options=options,
            row=0,
        )
        select.callback = self._on_select
        self.add_item(select)

        back_btn = Button(label="← Back", style=ButtonStyle.secondary, row=1)
        back_btn.callback = self._back
        self.add_item(back_btn)

        if self.total_pages > 1:
            prev_btn = Button(
                label="◀",
                style=ButtonStyle.secondary,
                disabled=self.page <= 0,
                row=1,
            )
            prev_btn.callback = self._prev
            self.add_item(prev_btn)

            next_btn = Button(
                label="▶",
                style=ButtonStyle.secondary,
                disabled=self.page >= self.total_pages - 1,
                row=1,
            )
            next_btn.callback = self._next
            self.add_item(next_btn)

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This menu isn't yours.", ephemeral=True)
            return False
        return True

    async def _on_select(self, interaction: Interaction) -> None:
        role_id = int(interaction.data["values"][0])
        role = interaction.guild.get_role(role_id)

        if role is None:
            await interaction.response.edit_message(
                content="That team role no longer exists. Please try again.", view=None,
            )
            return

        previous = self.current_pick
        try:
            await self.bot.db.upsert_wc_prediction(
                user_id=self.user_id,
                guild_id=interaction.guild.id,
                team_role_id=role.id,
                team_name=role.name,
            )
        except Exception as exc:
            logger.error("Failed to upsert prediction for %s: %s", self.user_id, exc)
            await interaction.response.edit_message(
                content="Something went wrong saving your prediction. Please try again.",
                view=None,
            )
            return

        await interaction.response.edit_message(
            content=f"Saved! Your World Cup pick is **{role.name}**.", view=None,
        )
        self.stop()
        await _log_pick(interaction, role, previous)

    async def _back(self, interaction: Interaction) -> None:
        view = WCPredictMenuView(
            teams=self.teams,
            user_id=self.user_id,
            bot=self.bot,
            current_pick=self.current_pick,
        )
        await interaction.response.edit_message(content="What would you like to do?", view=view)

    async def _prev(self, interaction: Interaction) -> None:
        self.page = max(0, self.page - 1)
        self._rebuild()
        await interaction.response.edit_message(view=self)

    async def _next(self, interaction: Interaction) -> None:
        self.page = min(self.total_pages - 1, self.page + 1)
        self._rebuild()
        await interaction.response.edit_message(view=self)

    async def on_timeout(self) -> None:
        logger.debug("WCPredictTeamSelectView timed out for user %s", self.user_id)


async def _get_log_channel(guild: discord.Guild) -> discord.TextChannel | None:
    channel = guild.get_channel(WC_PREDICT_LOG_CHANNEL_ID)
    if channel is None:
        logger.warning(
            "Log channel %s not found in guild %s", WC_PREDICT_LOG_CHANNEL_ID, guild.id,
        )
    return channel


async def _log_pick(
    interaction: Interaction,
    role: discord.Role,
    previous: discord.Role | None,
) -> None:
    channel = await _get_log_channel(interaction.guild)
    if channel is None:
        return

    embed = discord.Embed(color=role.color or discord.Color.blurple())
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    if previous and previous.id != role.id:
        embed.description = (
            f"**{interaction.user}** changed their World Cup pick "
            f"from **{previous.name}** to **{role.name}**."
        )
    else:
        embed.description = (
            f"**{interaction.user}** predicted **{role.name}** to win the World Cup."
        )

    try:
        await channel.send(embed=embed)
    except (discord.Forbidden, discord.HTTPException) as exc:
        logger.error(
            "Failed to send prediction log to channel %s: %s",
            WC_PREDICT_LOG_CHANNEL_ID, exc,
        )


async def _log_clear(interaction: Interaction, role: discord.Role) -> None:
    channel = await _get_log_channel(interaction.guild)
    if channel is None:
        return

    embed = discord.Embed(color=discord.Color.red())
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    embed.description = (
        f"**{interaction.user}** cleared their World Cup prediction (was **{role.name}**)."
    )

    try:
        await channel.send(embed=embed)
    except (discord.Forbidden, discord.HTTPException) as exc:
        logger.error(
            "Failed to send prediction-clear log to channel %s: %s",
            WC_PREDICT_LOG_CHANNEL_ID, exc,
        )
