"""Modals for the tasks cog — task creation form."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import Interaction, TextStyle
from discord.ui import Modal, TextInput

from cogs.utils.embeds import green_embed, red_embed

from .config import TASKS_CHANNEL_ID
from .views import TaskView, build_task_embed

if TYPE_CHECKING:
    from hablemos import Hablemos

logger = logging.getLogger(__name__)


class TaskCreateModal(Modal, title="Create a Task"):
    """Modal form for creating a new task."""

    task_title = TextInput(
        label="Title",
        placeholder="What needs to be done?",
        required=True,
        max_length=256,
    )

    description = TextInput(
        label="Description",
        placeholder="Add details, context, links…",
        required=False,
        max_length=1024,
        style=TextStyle.paragraph,
    )

    def __init__(self, assignees: list[discord.Member] | None = None):
        super().__init__()
        self.assignees = assignees or []

    async def on_submit(self, interaction: Interaction) -> None:
        """Create the task, post embed, and ping assignees."""
        bot: Hablemos = interaction.client  # type: ignore[assignment]
        assignee_ids = [m.id for m in self.assignees]

        task = await bot.db.create_task(
            guild_id=interaction.guild_id,
            title=str(self.task_title),
            description=str(self.description),
            created_by=interaction.user.id,
            assignee_ids=assignee_ids,
        )

        embed = build_task_embed(task, interaction.guild)
        view = TaskView(task["id"])

        channel = bot.get_channel(TASKS_CHANNEL_ID)
        if not channel:
            await interaction.response.send_message(
                embed=red_embed("Tasks channel not configured. Set `TASKS_CHANNEL_ID`."),
                ephemeral=True,
            )
            return

        msg = await channel.send(embed=embed, view=view)
        await bot.db.update_task_message(task["id"], msg.id)

        if self.assignees:
            mentions = " ".join(m.mention for m in self.assignees)
            await channel.send(
                f"📌 {mentions} — new task: **{self.task_title}** (#{task['id']})",
                allowed_mentions=discord.AllowedMentions(users=True),
            )

        await interaction.response.send_message(
            embed=green_embed(f"Task **#{task['id']}** created in {channel.mention}."),
            ephemeral=True,
        )
        logger.info("Task #%s created by %s", task["id"], interaction.user)
