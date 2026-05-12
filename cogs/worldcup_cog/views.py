"""Views for the World Cup cog — team role picker with menu."""
import logging

import discord
from discord import ButtonStyle, Interaction
from discord.ui import Button, Select, View

from .config import WORLD_CUP_LOG_CHANNEL_ID

logger = logging.getLogger(__name__)

TEAMS_PER_PAGE = 24


class WorldCupMenuView(View):
    """Initial menu: Pick a team (always) + Remove my team (only if user has one)."""

    def __init__(
        self,
        teams: list[discord.Role],
        user_id: int,
        current_team: discord.Role | None = None,
        timeout: float = 180,
    ):
        super().__init__(timeout=timeout)
        self.teams = teams
        self.user_id = user_id
        self.current_team = current_team

        pick_btn = Button(label="Pick a team", style=ButtonStyle.primary)
        pick_btn.callback = self._pick
        self.add_item(pick_btn)

        if current_team is not None:
            remove_btn = Button(
                label=f"Remove {current_team.name}",
                style=ButtonStyle.danger,
            )
            remove_btn.callback = self._remove
            self.add_item(remove_btn)

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This menu isn't yours.", ephemeral=True)
            return False
        return True

    async def _pick(self, interaction: Interaction) -> None:
        view = TeamSelectView(
            teams=self.teams,
            user_id=self.user_id,
            current_team=self.current_team,
        )
        await interaction.response.edit_message(content="Select your World Cup team:", view=view)

    async def _remove(self, interaction: Interaction) -> None:
        role = self.current_team
        try:
            await interaction.user.remove_roles(role, reason="World Cup team removal")
        except discord.Forbidden:
            logger.warning("Missing permissions to remove role %s from %s", role.name, interaction.user)
            await interaction.response.edit_message(
                content="I don't have permission to remove that role.", view=None
            )
            return
        except discord.HTTPException as exc:
            logger.error("HTTP error removing role %s: %s", role.name, exc)
            await interaction.response.edit_message(content="Something went wrong. Please try again.", view=None)
            return

        await interaction.response.edit_message(content=f"Removed **{role.name}**.", view=None)
        self.stop()
        await _log_removal(interaction, role)

    async def on_timeout(self) -> None:
        logger.debug("WorldCupMenuView timed out for user %s", self.user_id)


class TeamSelectView(View):
    """Paginated select for picking a team role."""

    def __init__(
        self,
        teams: list[discord.Role],
        user_id: int,
        current_team: discord.Role | None = None,
        page: int = 0,
        timeout: float = 180,
    ):
        super().__init__(timeout=timeout)
        self.teams = teams
        self.user_id = user_id
        self.current_team = current_team
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
                default=self.current_team is not None and role.id == self.current_team.id,
            )
            for role in page_teams
        ]
        select = Select(
            placeholder=f"Choose your team... (page {self.page + 1}/{self.total_pages})",
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
        member = interaction.user
        role = interaction.guild.get_role(role_id)

        if role is None:
            await interaction.response.edit_message(content="Role not found. Please try again.", view=None)
            return

        previous = next((r for r in member.roles if r.name.startswith("Team ") and r.id != role_id), None)
        to_remove = [r for r in member.roles if r.name.startswith("Team ") and r.id != role_id]

        try:
            if to_remove:
                await member.remove_roles(*to_remove, reason="World Cup team switch")
            await member.add_roles(role, reason="World Cup team selection")
        except discord.Forbidden:
            logger.warning("Missing permissions to assign role %s to %s", role.name, member)
            await interaction.response.edit_message(
                content="I don't have permission to assign that role.", view=None
            )
            return
        except discord.HTTPException as exc:
            logger.error("HTTP error assigning role %s: %s", role.name, exc)
            await interaction.response.edit_message(content="Something went wrong. Please try again.", view=None)
            return

        await interaction.response.edit_message(content=f"You've been assigned **{role.name}**.", view=None)
        self.stop()
        await _log_assignment(interaction, role, previous)

    async def _back(self, interaction: Interaction) -> None:
        view = WorldCupMenuView(
            teams=self.teams,
            user_id=self.user_id,
            current_team=self.current_team,
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
        logger.debug("TeamSelectView timed out for user %s", self.user_id)


async def _get_log_channel(guild: discord.Guild) -> discord.TextChannel | None:
    channel = guild.get_channel(WORLD_CUP_LOG_CHANNEL_ID)
    if channel is None:
        logger.warning("Log channel %s not found in guild %s", WORLD_CUP_LOG_CHANNEL_ID, guild.id)
    return channel


async def _log_assignment(
    interaction: Interaction,
    role: discord.Role,
    previous: discord.Role | None,
) -> None:
    channel = await _get_log_channel(interaction.guild)
    if channel is None:
        return

    embed = discord.Embed(color=role.color or discord.Color.blurple())
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    if previous:
        embed.description = f"**{interaction.user}** switched from **{previous.name}** to **{role.name}**."
    else:
        embed.description = f"**{interaction.user}** assigned themselves **{role.name}**."

    try:
        await channel.send(embed=embed)
    except (discord.Forbidden, discord.HTTPException) as exc:
        logger.error("Failed to send assignment log to channel %s: %s", WORLD_CUP_LOG_CHANNEL_ID, exc)


async def _log_removal(interaction: Interaction, role: discord.Role) -> None:
    channel = await _get_log_channel(interaction.guild)
    if channel is None:
        return

    embed = discord.Embed(color=discord.Color.red())
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    embed.description = f"**{interaction.user}** removed **{role.name}**."

    try:
        await channel.send(embed=embed)
    except (discord.Forbidden, discord.HTTPException) as exc:
        logger.error("Failed to send removal log to channel %s: %s", WORLD_CUP_LOG_CHANNEL_ID, exc)
