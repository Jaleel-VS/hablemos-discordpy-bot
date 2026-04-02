"""Task manager cog — admin task tracking with interactive embeds."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import Interaction, app_commands
from discord.ext import commands

from base_cog import BaseCog
from cogs.utils.embeds import green_embed, red_embed

from .config import (
    STATUS_CHOICES,
    STATUSES,
    TASKS_CATEGORY_ID,
    TASKS_CHANNEL_ID,
)
from .modals import TaskCreateModal
from .views import TaskView

if TYPE_CHECKING:
    from hablemos import Hablemos

logger = logging.getLogger(__name__)


def _is_tasks_readable_channel(interaction: Interaction) -> bool:
    """Check if the command is in the tasks channel or its read-only category."""
    if interaction.channel_id == TASKS_CHANNEL_ID:
        return True
    if TASKS_CATEGORY_ID and hasattr(interaction.channel, "category_id"):
        return interaction.channel.category_id == TASKS_CATEGORY_ID
    return False


class TaskManager(BaseCog):
    """Admin task management with interactive Discord UI."""

    def __init__(self, bot: Hablemos):
        super().__init__(bot)
        self._register_persistent_views()

    def _register_persistent_views(self) -> None:
        """Register a dynamic persistent view handler for task components."""
        # We can't pre-register views for every task ID, so we use
        # a listener in on_interaction to handle them dynamically.
        pass

    @commands.Cog.listener()
    async def on_interaction(self, interaction: Interaction) -> None:
        """Handle persistent task view interactions dynamically."""
        if interaction.type != discord.InteractionType.component:
            return

        custom_id = interaction.data.get("custom_id", "")
        if not custom_id.startswith(("task_status:", "task_assign:")):
            return

        # Parse task ID from custom_id
        try:
            task_id = int(custom_id.split(":")[1])
        except (IndexError, ValueError):
            return

        # Reconstruct the view and let it handle the interaction
        view = TaskView(task_id)
        # Find the matching component and dispatch
        for item in view.children:
            if item.custom_id == custom_id:
                await item.callback(interaction)
                return

    # --- Slash commands (admin only) ---

    task_group = app_commands.Group(
        name="task",
        description="Task management commands",
        default_permissions=discord.Permissions(manage_guild=True),
    )

    @task_group.command(name="create", description="Create a new task")
    @app_commands.describe(
        assignee1="Assign a member",
        assignee2="Assign a second member",
        assignee3="Assign a third member",
    )
    async def task_create(
        self,
        interaction: Interaction,
        assignee1: discord.Member | None = None,
        assignee2: discord.Member | None = None,
        assignee3: discord.Member | None = None,
    ) -> None:
        """Open a modal form to create a task."""
        assignees = [m for m in (assignee1, assignee2, assignee3) if m]
        await interaction.response.send_modal(TaskCreateModal(assignees=assignees))

    @task_group.command(name="list", description="List tasks")
    @app_commands.describe(
        status="Filter by status",
        assignee="Filter by assignee",
    )
    @app_commands.choices(
        status=[app_commands.Choice(name=label, value=key) for label, key in STATUS_CHOICES],
    )
    async def task_list(
        self,
        interaction: Interaction,
        status: str | None = None,
        assignee: discord.Member | None = None,
    ) -> None:
        """List tasks with optional filters. Works in tasks channel or category."""
        if not _is_tasks_readable_channel(interaction):
            await interaction.response.send_message(
                embed=red_embed("Use this command in the tasks channel or its category."),
                ephemeral=True,
            )
            return

        tasks = await self.bot.db.list_tasks(
            guild_id=interaction.guild_id,
            status=status,
            assignee_id=assignee.id if assignee else None,
        )

        if not tasks:
            await interaction.response.send_message(
                embed=red_embed("No tasks found."), ephemeral=True,
            )
            return

        # Group by status
        grouped: dict[str, list[dict]] = {}
        for t in tasks:
            grouped.setdefault(t["status"], []).append(t)

        lines = []
        for status_key, status_tasks in grouped.items():
            emoji, label, _ = STATUSES.get(status_key, ("❓", status_key, 0))
            lines.append(f"**{emoji} {label}**")
            for t in status_tasks[:10]:
                assignee_ids = t.get("assignee_ids") or []
                assignee_str = (
                    ", ".join(f"<@{uid}>" for uid in assignee_ids)
                    if assignee_ids
                    else "unassigned"
                )
                lines.append(f"  `#{t['id']}` {t['title']} — {assignee_str}")
            if len(status_tasks) > 10:
                lines.append(f"  *…and {len(status_tasks) - 10} more*")
            lines.append("")

        embed = discord.Embed(
            title="📋 Tasks",
            description="\n".join(lines),
            color=0x3498DB,
        )
        embed.set_footer(text=f"{len(tasks)} task(s)")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @task_group.command(name="delete", description="Delete a task")
    @app_commands.describe(task_id="Task ID number")
    async def task_delete(
        self,
        interaction: Interaction,
        task_id: int,
    ) -> None:
        """Delete a task and remove its embed from the tasks channel."""
        task = await self.bot.db.get_task(task_id)
        if not task or task["guild_id"] != interaction.guild_id:
            await interaction.response.send_message(
                embed=red_embed("Task not found."), ephemeral=True,
            )
            return

        # Try to delete the message from the tasks channel
        if task.get("message_id"):
            channel = self.bot.get_channel(TASKS_CHANNEL_ID)
            if channel:
                try:
                    msg = await channel.fetch_message(task["message_id"])
                    await msg.delete()
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    pass

        await self.bot.db.delete_task(task_id)
        await interaction.response.send_message(
            embed=green_embed(f"Task **#{task_id}** deleted."), ephemeral=True,
        )
        logger.info("Task #%s deleted by %s", task_id, interaction.user)

    @task_group.command(name="board", description="Show task board overview")
    async def task_board(self, interaction: Interaction) -> None:
        """Show a kanban-style board with all tasks grouped by status."""
        if not _is_tasks_readable_channel(interaction):
            await interaction.response.send_message(
                embed=red_embed("Use this command in the tasks channel or its category."),
                ephemeral=True,
            )
            return

        tasks = await self.bot.db.list_tasks(guild_id=interaction.guild_id)

        embeds = []
        for status_key, (emoji, label, color) in STATUSES.items():
            status_tasks = [t for t in tasks if t["status"] == status_key]
            lines = []
            for t in status_tasks[:15]:
                assignee_ids = t.get("assignee_ids") or []
                assignee_str = (
                    ", ".join(f"<@{uid}>" for uid in assignee_ids)
                    if assignee_ids
                    else "*unassigned*"
                )
                lines.append(f"`#{t['id']}` **{t['title']}**\n↳ {assignee_str}")

            embed = discord.Embed(
                title=f"{emoji} {label} ({len(status_tasks)})",
                description="\n\n".join(lines) if lines else "*No tasks*",
                color=color,
            )
            embeds.append(embed)

        await interaction.response.send_message(embeds=embeds, ephemeral=True)


async def setup(bot: Hablemos) -> None:
    """Load the TaskManager cog."""
    await bot.add_cog(TaskManager(bot))
