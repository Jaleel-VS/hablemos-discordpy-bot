"""Modals for the tasks cog — task creation form."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import Interaction, RadioGroupOption, TextStyle
from discord.ui import Label, Modal, RadioGroup, TextInput

from cogs.utils.embeds import green_embed, red_embed

from .config import TASKS_CHANNEL_ID
from .views import TaskView, build_task_embed

if TYPE_CHECKING:
    from hablemos import Hablemos

logger = logging.getLogger(__name__)


def _build_member_options(
    members: list[discord.Member],
    invoker: discord.Member,
) -> list[RadioGroupOption]:
    """Build radio options from role members, invoker first with (self) tag."""
    options = [RadioGroupOption(label="None", value="0")]
    # Invoker first
    options.append(RadioGroupOption(
        label=f"{invoker.display_name} (self)",
        value=str(invoker.id),
    ))
    for m in members:
        if m.id != invoker.id:
            options.append(RadioGroupOption(label=m.display_name, value=str(m.id)))
    return options


class TaskCreateModal(Modal, title="Create a Task"):
    """Modal form for creating a new task with assignee radio buttons."""

    def __init__(self, members: list[discord.Member], invoker: discord.Member):
        super().__init__()
        self.member_options = _build_member_options(members, invoker)

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
            text="Assignee 1",
            component=RadioGroup(options=self.member_options),
        ))
        self.add_item(Label(
            text="Assignee 2",
            component=RadioGroup(options=self.member_options),
        ))
        self.add_item(Label(
            text="Assignee 3",
            component=RadioGroup(options=self.member_options),
        ))

    async def on_submit(self, interaction: Interaction) -> None:
        """Create the task, post embed, and ping assignees."""
        bot: Hablemos = interaction.client  # type: ignore[assignment]

        # Extract values from dynamic components
        title_component = self.children[0].component
        desc_component = self.children[1].component
        task_title = title_component.value or ""
        description = desc_component.value or ""

        # Collect unique non-zero assignee IDs
        assignee_ids: list[int] = []
        for i in range(2, 5):
            radio = self.children[i].component
            if radio.value and radio.value != "0":
                uid = int(radio.value)
                if uid not in assignee_ids:
                    assignee_ids.append(uid)

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
