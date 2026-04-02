"""Persistent views for task embeds — survive bot restarts."""
import logging

import discord
from discord import Interaction, SelectOption
from discord.ui import Select, UserSelect, View

from .config import STATUSES

logger = logging.getLogger(__name__)


def build_task_embed(task: dict, guild: discord.Guild) -> discord.Embed:
    """Build a rich embed for a task."""
    status_key = task["status"]
    emoji, label, color = STATUSES.get(status_key, ("❓", status_key, 0x95A5A6))

    embed = discord.Embed(
        title=f"{emoji}  {task['title']}",
        description=task["description"] or "*No description*",
        color=color,
    )
    embed.add_field(name="Status", value=f"{emoji} {label}", inline=True)
    embed.add_field(name="ID", value=f"`#{task['id']}`", inline=True)

    # Assignees
    assignee_ids: list[int] = task.get("assignee_ids") or []
    if assignee_ids:
        mentions = []
        for uid in assignee_ids:
            member = guild.get_member(uid)
            mentions.append(member.mention if member else f"<@{uid}>")
        embed.add_field(name="Assigned to", value=", ".join(mentions), inline=False)
    else:
        embed.add_field(name="Assigned to", value="*Unassigned*", inline=False)

    # Footer with creator and timestamps
    creator = guild.get_member(task["created_by"])
    creator_name = creator.display_name if creator else str(task["created_by"])
    embed.set_footer(text=f"Created by {creator_name}")
    embed.timestamp = task["created_at"]

    return embed


class TaskStatusSelect(Select):
    """Dropdown to change task status."""

    def __init__(self, task_id: int):
        options = [
            SelectOption(
                label=label,
                value=key,
                emoji=emoji,
                default=False,
            )
            for key, (emoji, label, _) in STATUSES.items()
        ]
        super().__init__(
            placeholder="Change status…",
            options=options,
            custom_id=f"task_status:{task_id}",
        )
        self.task_id = task_id

    async def callback(self, interaction: Interaction) -> None:
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "You don't have permission to do that.", ephemeral=True,
            )
            return

        new_status = self.values[0]
        task = await interaction.client.db.update_task_status(self.task_id, new_status)
        if not task:
            await interaction.response.send_message("Task not found.", ephemeral=True)
            return

        embed = build_task_embed(task, interaction.guild)
        await interaction.response.edit_message(embed=embed)
        logger.info(
            "Task #%s status changed to %s by %s",
            self.task_id, new_status, interaction.user,
        )


class TaskAssignSelect(UserSelect):
    """User select to reassign a task (up to 3)."""

    def __init__(self, task_id: int):
        super().__init__(
            placeholder="Assign members (up to 3)…",
            custom_id=f"task_assign:{task_id}",
            min_values=0,
            max_values=3,
        )
        self.task_id = task_id

    async def callback(self, interaction: Interaction) -> None:
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "You don't have permission to do that.", ephemeral=True,
            )
            return

        new_ids = [u.id for u in self.values]
        task = await interaction.client.db.update_task_assignees(self.task_id, new_ids)
        if not task:
            await interaction.response.send_message("Task not found.", ephemeral=True)
            return

        embed = build_task_embed(task, interaction.guild)
        await interaction.response.edit_message(embed=embed)

        # Ping newly assigned members
        if new_ids:
            mentions = " ".join(f"<@{uid}>" for uid in new_ids)
            await interaction.followup.send(
                f"📌 {mentions} — you've been assigned to **{task['title']}** (#{self.task_id})",
                allowed_mentions=discord.AllowedMentions(users=True),
            )

        logger.info(
            "Task #%s reassigned to %s by %s",
            self.task_id, new_ids, interaction.user,
        )


class TaskView(View):
    """Persistent view attached to each task embed."""

    def __init__(self, task_id: int):
        super().__init__(timeout=None)
        self.add_item(TaskStatusSelect(task_id))
        self.add_item(TaskAssignSelect(task_id))
