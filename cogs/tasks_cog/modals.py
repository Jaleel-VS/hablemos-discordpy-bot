"""Modals for the tasks cog — task creation form."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import CheckboxGroupOption, Interaction, TextStyle
from discord.ui import CheckboxGroup, Label, Modal, TextInput

from cogs.utils.embeds import green_embed, red_embed

from .config import ASSIGNABLE_MEMBER_IDS, TASKS_CHANNEL_ID
from .views import TaskView, build_task_embed

if TYPE_CHECKING:
    from hablemos import Hablemos

logger = logging.getLogger(__name__)


def _build_assignee_options(
    guild: discord.Guild,
    invoker: discord.Member,
) -> list[CheckboxGroupOption]:
    """Build checkbox options from hardcoded member IDs, invoker tagged with (self)."""
    options = []
    for uid in ASSIGNABLE_MEMBER_IDS:
        member = guild.get_member(uid)
        name = member.display_name if member else str(uid)
        if uid == invoker.id:
            name = f"{name} (self)"
        options.append(CheckboxGroupOption(label=name, value=str(uid)))
    return options


class TaskCreateModal(Modal, title="Create a Task"):
    """Modal form for creating a new task with checkbox assignees."""

    def __init__(self, guild: discord.Guild, invoker: discord.Member):
        super().__init__()
        self.add_item(Label(
            text="Title",
            component=TextInput(
                placeholder="What needs to be done?",
                required=True,
                max_length=256,
            ),
        ))
        self.add_item(Label(
            text="Description",
            component=TextInput(
                placeholder="Add details, context, links…",
                required=False,
                max_length=1024,
                style=TextStyle.paragraph,
            ),
        ))
        self.add_item(Label(
            text="Assignees",
            component=CheckboxGroup(
                options=_build_assignee_options(guild, invoker),
                min_values=0,
                max_values=len(ASSIGNABLE_MEMBER_IDS),
            ),
        ))

    async def on_submit(self, interaction: Interaction) -> None:
        """Create the task, post embed, and ping assignees."""
        bot: Hablemos = interaction.client  # type: ignore[assignment]

        task_title = self.children[0].component.value or ""
        description = self.children[1].component.value or ""

        checkbox = self.children[2].component
        assignee_ids = [int(v) for v in checkbox.values] if checkbox.values else []

        task = await bot.db.create_task(
            guild_id=interaction.guild_id,
            title=task_title,
            description=description,
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

        if assignee_ids:
            mentions = " ".join(f"<@{uid}>" for uid in assignee_ids)
            await channel.send(
                f"📌 {mentions} — new task: **{task_title}** (#{task['id']})",
                allowed_mentions=discord.AllowedMentions(users=True),
            )

        await interaction.response.send_message(
            embed=green_embed(f"Task **#{task['id']}** created in {channel.mention}."),
            ephemeral=True,
        )
        logger.info("Task #%s created by %s", task["id"], interaction.user)
