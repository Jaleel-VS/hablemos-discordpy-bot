"""Views for the World Cup cog — paginated team role picker."""
import logging

import discord
from discord import ButtonStyle, Interaction
from discord.ui import Button, Select, View

from .config import WORLD_CUP_LOG_CHANNEL_ID

logger = logging.getLogger(__name__)

TEAMS_PER_PAGE = 24


class TeamSelectView(View):
    """Paginated select menu for choosing a World Cup team role."""

    def __init__(
        self,
        teams: list[discord.Role],
        user_id: int,
        page: int = 0,
        timeout: float = 180,
    ):
        super().__init__(timeout=timeout)
        self.teams = teams
        self.user_id = user_id
        self.page = page
        self.total_pages = max(1, (len(teams) - 1) // TEAMS_PER_PAGE + 1)
        self._rebuild()

    def _rebuild(self) -> None:
        self.clear_items()
        start = self.page * TEAMS_PER_PAGE
        page_teams = self.teams[start : start + TEAMS_PER_PAGE]

        options = [
            discord.SelectOption(label=role.name, value=str(role.id))
            for role in page_teams
        ]
        select = Select(
            placeholder=f"Elige tu equipo... (página {self.page + 1}/{self.total_pages})",
            options=options,
            row=0,
        )
        select.callback = self._on_select
        self.add_item(select)

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
            await interaction.response.send_message(
                "Este menú no es tuyo.", ephemeral=True
            )
            return False
        return True

    async def _on_select(self, interaction: Interaction) -> None:
        role_id = int(interaction.data["values"][0])
        guild = interaction.guild
        member = interaction.user

        role = guild.get_role(role_id)
        if role is None:
            await interaction.response.send_message(
                "No encontré ese rol. Intenta de nuevo.", ephemeral=True
            )
            return

        # Remove any existing Team roles before assigning the new one
        team_roles_to_remove = [
            r for r in member.roles if r.name.startswith("Team ") and r.id != role_id
        ]
        try:
            if team_roles_to_remove:
                await member.remove_roles(*team_roles_to_remove, reason="World Cup team switch")
            await member.add_roles(role, reason="World Cup team selection")
        except discord.Forbidden:
            logger.warning("Missing permissions to assign role %s to %s", role.name, member)
            await interaction.response.send_message(
                "No tengo permisos para asignarte ese rol.", ephemeral=True
            )
            return
        except discord.HTTPException as exc:
            logger.error("HTTP error assigning role %s: %s", role.name, exc)
            await interaction.response.send_message(
                "Ocurrió un error. Intenta de nuevo.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"Se te asignó el rol **{role.name}**.", ephemeral=True
        )
        self.stop()

        await _log_role_assignment(interaction, role)

    async def _prev(self, interaction: Interaction) -> None:
        self.page = max(0, self.page - 1)
        self._rebuild()
        await interaction.response.edit_message(view=self)

    async def _next(self, interaction: Interaction) -> None:
        self.page = min(self.total_pages - 1, self.page + 1)
        self._rebuild()
        await interaction.response.edit_message(view=self)

    async def on_timeout(self) -> None:
        logger.debug("TeamSelectView timed out for user %s", self.user_id)


async def _log_role_assignment(interaction: Interaction, role: discord.Role) -> None:
    log_channel = interaction.guild.get_channel(WORLD_CUP_LOG_CHANNEL_ID)
    if log_channel is None:
        logger.warning("Log channel %s not found in guild %s", WORLD_CUP_LOG_CHANNEL_ID, interaction.guild.id)
        return

    embed = discord.Embed(color=role.color or discord.Color.blurple())
    embed.description = f"**{interaction.user}** se puso el rol **{role.name}**."
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    try:
        await log_channel.send(embed=embed)
    except (discord.Forbidden, discord.HTTPException) as exc:
        logger.error("Failed to log role assignment to channel %s: %s", WORLD_CUP_LOG_CHANNEL_ID, exc)
