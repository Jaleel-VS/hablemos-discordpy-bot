"""Views for the Tickets cog — forum subscription picker."""

import logging

import discord
from discord.ui import Select, View

logger = logging.getLogger(__name__)


class TicketSubView(View):
    """Select menu letting a user toggle per-forum ticket subscriptions."""

    def __init__(
        self,
        *,
        user_id: int,
        forums: list[tuple[int, str]],
        subscribed_ids: set[int],
        timeout: float = 120,
    ):
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.forums = forums  # [(forum_id, display_name), ...]
        self.subscribed_ids = subscribed_ids
        self._build_select()

    def _build_select(self) -> None:
        options = []
        for forum_id, name in self.forums:
            is_subbed = forum_id in self.subscribed_ids
            options.append(
                discord.SelectOption(
                    label=name,
                    value=str(forum_id),
                    description="Subscribed ✓" if is_subbed else "Not subscribed",
                    emoji="🔔" if is_subbed else "🔕",
                    default=is_subbed,
                ),
            )

        select = Select(
            placeholder="Select forums to subscribe to...",
            options=options,
            min_values=0,
            max_values=len(options),
            row=0,
        )
        select.callback = self._on_select
        self.add_item(select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This menu isn't yours.", ephemeral=True,
            )
            return False
        return True

    async def _on_select(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.edit_message(
                content="This only works in a server.", view=None,
            )
            return

        data = interaction.data
        selected_values: list[str] = data.get("values", []) if data else []
        selected_ids = {int(v) for v in selected_values}

        guild_id = interaction.guild.id
        user_id = interaction.user.id
        db = interaction.client.db  # type: ignore[attr-defined]

        # Determine additions and removals
        to_add = selected_ids - self.subscribed_ids
        to_remove = self.subscribed_ids - selected_ids

        for forum_id in to_add:
            await db.add_ticket_subscription(user_id, guild_id, forum_id)
        for forum_id in to_remove:
            await db.remove_ticket_subscription(user_id, guild_id, forum_id)

        # Update local state and rebuild
        self.subscribed_ids = selected_ids

        # Build response
        if selected_ids:
            forum_names = [
                name for fid, name in self.forums if fid in selected_ids
            ]
            listing = ", ".join(f"**#{n}**" for n in forum_names)
            description = f"🔔 You'll be pinged for new tickets in: {listing}"
        else:
            description = "🔕 You won't be pinged for any new tickets."

        embed = discord.Embed(
            description=description,
            color=discord.Color.green() if selected_ids else discord.Color.orange(),
        )

        # Rebuild select to reflect new state
        self.clear_items()
        self._build_select()

        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self) -> None:
        logger.debug("TicketSubView timed out for user %s", self.user_id)
