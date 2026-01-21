"""
Discord views (buttons, selects) for website management
"""
import discord
from discord import Interaction, Embed, ButtonStyle
from discord.ui import View, Button, Select, button, select
import logging
from typing import Optional, Callable, Awaitable

from .modals import AddPodcastModalFull, EditPodcastModal

logger = logging.getLogger(__name__)

# Constants
ITEMS_PER_PAGE = 5


class MainManageView(View):
    """Main management menu with resource type buttons"""

    def __init__(self, api_client, timeout: float = 180):
        super().__init__(timeout=timeout)
        self.api_client = api_client

    @button(label="Podcasts", style=ButtonStyle.primary, emoji="🎙️")
    async def podcasts_button(self, interaction: Interaction, btn: Button):
        """Open podcast management menu"""
        view = PodcastMenuView(self.api_client)
        embed = Embed(
            title="Podcast Management",
            description="Choose an action:",
            color=discord.Color.orange()
        )
        await interaction.response.edit_message(embed=embed, view=view)

    @button(label="Videos", style=ButtonStyle.secondary, emoji="🎬", disabled=True)
    async def videos_button(self, interaction: Interaction, btn: Button):
        """Placeholder for future video management"""
        await interaction.response.send_message("Video management coming soon!", ephemeral=True)

    @button(label="Books", style=ButtonStyle.secondary, emoji="📚", disabled=True)
    async def books_button(self, interaction: Interaction, btn: Button):
        """Placeholder for future book management"""
        await interaction.response.send_message("Book management coming soon!", ephemeral=True)

    @button(label="Close", style=ButtonStyle.danger, emoji="✖️", row=1)
    async def close_button(self, interaction: Interaction, btn: Button):
        """Close the management panel"""
        await interaction.response.edit_message(
            content="Management panel closed.",
            embed=None,
            view=None
        )
        self.stop()


class PodcastMenuView(View):
    """Podcast management menu"""

    def __init__(self, api_client, timeout: float = 180):
        super().__init__(timeout=timeout)
        self.api_client = api_client

    @button(label="Add Podcast", style=ButtonStyle.success, emoji="➕")
    async def add_button(self, interaction: Interaction, btn: Button):
        """Open modal to add a new podcast"""
        modal = AddPodcastModalFull(self.api_client)
        await interaction.response.send_modal(modal)

    @button(label="List Podcasts", style=ButtonStyle.primary, emoji="📋")
    async def list_button(self, interaction: Interaction, btn: Button):
        """Show paginated list of podcasts"""
        await interaction.response.defer(ephemeral=True)

        try:
            podcasts = await self.api_client.get_podcasts(include_archived=True)

            if not podcasts:
                embed = Embed(
                    title="No Podcasts",
                    description="No podcasts have been added yet.",
                    color=discord.Color.blue()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            view = PodcastListView(self.api_client, podcasts, page=0)
            embed = view.create_embed()
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

        except Exception as e:
            logger.error(f"Error listing podcasts: {e}", exc_info=True)
            await interaction.followup.send(f"Error loading podcasts: {e}", ephemeral=True)

    @button(label="View Reports", style=ButtonStyle.secondary, emoji="🚩")
    async def reports_button(self, interaction: Interaction, btn: Button):
        """Show podcasts with dead link reports"""
        await interaction.response.defer(ephemeral=True)

        try:
            report_counts = await self.api_client.get_link_report_counts()

            if not report_counts:
                embed = Embed(
                    title="No Reports",
                    description="No dead link reports have been submitted.",
                    color=discord.Color.green()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # Get podcast details for reported ones
            podcasts = await self.api_client.get_podcasts(include_archived=True)
            podcast_map = {p.id: p for p in podcasts}

            embed = Embed(
                title="Dead Link Reports",
                description="Podcasts with reported dead links:",
                color=discord.Color.orange()
            )

            for report in sorted(report_counts, key=lambda r: r.count, reverse=True)[:10]:
                podcast = podcast_map.get(report.podcast_id)
                if podcast:
                    status = "🗄️ Archived" if podcast.archived else "✅ Active"
                    embed.add_field(
                        name=f"{podcast.title} ({report.count} reports)",
                        value=f"{status}\n[Link]({podcast.url})",
                        inline=False
                    )

            view = ReportActionsView(self.api_client, report_counts, podcast_map)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

        except Exception as e:
            logger.error(f"Error fetching reports: {e}", exc_info=True)
            await interaction.followup.send(f"Error loading reports: {e}", ephemeral=True)

    @button(label="Back", style=ButtonStyle.secondary, emoji="◀️", row=1)
    async def back_button(self, interaction: Interaction, btn: Button):
        """Go back to main menu"""
        view = MainManageView(self.api_client)
        embed = Embed(
            title="Website Management",
            description="Select a resource type to manage:",
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=view)


class PodcastListView(View):
    """Paginated list of podcasts with actions"""

    def __init__(self, api_client, podcasts: list, page: int = 0, timeout: float = 180):
        super().__init__(timeout=timeout)
        self.api_client = api_client
        self.podcasts = podcasts
        self.page = page
        self.total_pages = (len(podcasts) - 1) // ITEMS_PER_PAGE + 1 if podcasts else 1

        # Add podcast select dropdown
        self._update_select()
        self._update_buttons()

    def _update_select(self):
        """Update the podcast select dropdown for current page"""
        # Remove existing select if any
        for item in self.children[:]:
            if isinstance(item, Select):
                self.remove_item(item)

        start = self.page * ITEMS_PER_PAGE
        end = start + ITEMS_PER_PAGE
        page_podcasts = self.podcasts[start:end]

        if page_podcasts:
            options = [
                discord.SelectOption(
                    label=p.title[:100],
                    value=p.id,
                    description=f"{'🗄️ Archived' if p.archived else '✅ Active'} | {p.level.title()}",
                    emoji="🎙️"
                )
                for p in page_podcasts
            ]

            select_menu = Select(
                placeholder="Select a podcast to manage...",
                options=options,
                row=0
            )
            select_menu.callback = self.podcast_selected
            self.add_item(select_menu)

    def _update_buttons(self):
        """Update navigation button states"""
        for item in self.children:
            if isinstance(item, Button):
                if item.custom_id == "prev":
                    item.disabled = self.page <= 0
                elif item.custom_id == "next":
                    item.disabled = self.page >= self.total_pages - 1

    def create_embed(self) -> Embed:
        """Create the embed for current page"""
        embed = Embed(
            title="Podcasts",
            description=f"Page {self.page + 1}/{self.total_pages} • {len(self.podcasts)} total",
            color=discord.Color.blue()
        )

        start = self.page * ITEMS_PER_PAGE
        end = start + ITEMS_PER_PAGE

        for podcast in self.podcasts[start:end]:
            status = "🗄️" if podcast.archived else "✅"
            embed.add_field(
                name=f"{status} {podcast.title}",
                value=f"{podcast.level.title()} • {podcast.language.upper()} • {podcast.country}",
                inline=False
            )

        return embed

    async def podcast_selected(self, interaction: Interaction):
        """Handle podcast selection"""
        podcast_id = interaction.data['values'][0]
        podcast = next((p for p in self.podcasts if p.id == podcast_id), None)

        if not podcast:
            await interaction.response.send_message("Podcast not found.", ephemeral=True)
            return

        view = PodcastActionsView(self.api_client, podcast, parent_view=self)
        embed = Embed(
            title=podcast.title,
            description=podcast.description,
            color=discord.Color.orange() if podcast.archived else discord.Color.green(),
            url=podcast.url
        )
        embed.add_field(name="Language", value=podcast.language.upper(), inline=True)
        embed.add_field(name="Level", value=podcast.level.title(), inline=True)
        embed.add_field(name="Country", value=podcast.country, inline=True)
        embed.add_field(name="Topic", value=podcast.topic, inline=True)
        embed.add_field(name="Status", value="Archived" if podcast.archived else "Active", inline=True)
        if podcast.image_url:
            embed.set_thumbnail(url=podcast.image_url)

        await interaction.response.edit_message(embed=embed, view=view)

    @button(label="◀", style=ButtonStyle.secondary, custom_id="prev", row=1)
    async def prev_button(self, interaction: Interaction, btn: Button):
        """Previous page"""
        self.page = max(0, self.page - 1)
        self._update_select()
        self._update_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @button(label="▶", style=ButtonStyle.secondary, custom_id="next", row=1)
    async def next_button(self, interaction: Interaction, btn: Button):
        """Next page"""
        self.page = min(self.total_pages - 1, self.page + 1)
        self._update_select()
        self._update_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @button(label="Back to Menu", style=ButtonStyle.secondary, emoji="◀️", row=1)
    async def back_button(self, interaction: Interaction, btn: Button):
        """Go back to podcast menu"""
        view = PodcastMenuView(self.api_client)
        embed = Embed(
            title="Podcast Management",
            description="Choose an action:",
            color=discord.Color.orange()
        )
        await interaction.response.edit_message(embed=embed, view=view)


class PodcastActionsView(View):
    """Actions for a single podcast"""

    def __init__(self, api_client, podcast, parent_view=None, timeout: float = 180):
        super().__init__(timeout=timeout)
        self.api_client = api_client
        self.podcast = podcast
        self.parent_view = parent_view

        # Update archive button based on current state
        for item in self.children:
            if isinstance(item, Button) and item.custom_id == "archive":
                if podcast.archived:
                    item.label = "Unarchive"
                    item.style = ButtonStyle.success
                    item.emoji = "📤"
                else:
                    item.label = "Archive"
                    item.style = ButtonStyle.secondary
                    item.emoji = "🗄️"

    @button(label="Edit", style=ButtonStyle.primary, emoji="✏️")
    async def edit_button(self, interaction: Interaction, btn: Button):
        """Open edit modal"""
        modal = EditPodcastModal(self.api_client, self.podcast)
        await interaction.response.send_modal(modal)

    @button(label="Archive", style=ButtonStyle.secondary, emoji="🗄️", custom_id="archive")
    async def archive_button(self, interaction: Interaction, btn: Button):
        """Toggle archive status"""
        await interaction.response.defer(ephemeral=True)

        try:
            if self.podcast.archived:
                podcast = await self.api_client.unarchive_podcast(self.podcast.id)
                action = "unarchived"
            else:
                podcast = await self.api_client.archive_podcast(self.podcast.id)
                action = "archived"

            self.podcast = podcast

            embed = Embed(
                title=f"Podcast {action.title()}",
                description=f"**{podcast.title}** has been {action}.",
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info(f"User {interaction.user} {action} podcast: {podcast.title}")

        except Exception as e:
            logger.error(f"Error toggling archive: {e}", exc_info=True)
            await interaction.followup.send(f"Error: {e}", ephemeral=True)

    @button(label="Back to List", style=ButtonStyle.secondary, emoji="◀️", row=1)
    async def back_button(self, interaction: Interaction, btn: Button):
        """Go back to podcast list"""
        try:
            podcasts = await self.api_client.get_podcasts(include_archived=True)
            view = PodcastListView(self.api_client, podcasts, page=0)
            embed = view.create_embed()
            await interaction.response.edit_message(embed=embed, view=view)
        except Exception as e:
            logger.error(f"Error returning to list: {e}", exc_info=True)
            await interaction.response.send_message(f"Error: {e}", ephemeral=True)


class ConfirmDeleteView(View):
    """Confirmation dialog for deleting a podcast"""

    def __init__(self, api_client, podcast, timeout: float = 60):
        super().__init__(timeout=timeout)
        self.api_client = api_client
        self.podcast = podcast

    @button(label="Yes, Delete", style=ButtonStyle.danger, emoji="🗑️")
    async def confirm_button(self, interaction: Interaction, btn: Button):
        """Confirm deletion"""
        await interaction.response.defer(ephemeral=True)

        try:
            await self.api_client.delete_podcast(self.podcast.id)

            embed = Embed(
                title="Podcast Deleted",
                description=f"**{self.podcast.title}** has been deleted.",
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info(f"User {interaction.user} deleted podcast: {self.podcast.title}")

            # Go back to list
            podcasts = await self.api_client.get_podcasts(include_archived=True)
            if podcasts:
                view = PodcastListView(self.api_client, podcasts, page=0)
                embed = view.create_embed()
            else:
                view = PodcastMenuView(self.api_client)
                embed = Embed(
                    title="Podcast Management",
                    description="No podcasts remaining. Add one!",
                    color=discord.Color.orange()
                )
            await interaction.edit_original_response(embed=embed, view=view)

        except Exception as e:
            logger.error(f"Error deleting podcast: {e}", exc_info=True)
            await interaction.followup.send(f"Error: {e}", ephemeral=True)

    @button(label="Cancel", style=ButtonStyle.secondary, emoji="✖️")
    async def cancel_button(self, interaction: Interaction, btn: Button):
        """Cancel deletion"""
        view = PodcastActionsView(self.api_client, self.podcast)
        embed = Embed(
            title=self.podcast.title,
            description=self.podcast.description,
            color=discord.Color.orange() if self.podcast.archived else discord.Color.green(),
            url=self.podcast.url
        )
        embed.add_field(name="Status", value="Archived" if self.podcast.archived else "Active", inline=True)
        if self.podcast.image_url:
            embed.set_thumbnail(url=self.podcast.image_url)

        await interaction.response.edit_message(embed=embed, view=view)


class ReportActionsView(View):
    """Actions for managing reported podcasts"""

    def __init__(self, api_client, report_counts, podcast_map, timeout: float = 180):
        super().__init__(timeout=timeout)
        self.api_client = api_client
        self.report_counts = report_counts
        self.podcast_map = podcast_map

        # Add select for reported podcasts
        reported_podcasts = [
            podcast_map[r.podcast_id]
            for r in sorted(report_counts, key=lambda x: x.count, reverse=True)[:25]
            if r.podcast_id in podcast_map
        ]

        if reported_podcasts:
            options = [
                discord.SelectOption(
                    label=p.title[:100],
                    value=p.id,
                    description=f"{next((r.count for r in report_counts if r.podcast_id == p.id), 0)} reports",
                    emoji="🚩"
                )
                for p in reported_podcasts
            ]

            select_menu = Select(
                placeholder="Select a podcast to manage...",
                options=options,
                row=0
            )
            select_menu.callback = self.podcast_selected
            self.add_item(select_menu)

    async def podcast_selected(self, interaction: Interaction):
        """Handle podcast selection from reports"""
        podcast_id = interaction.data['values'][0]
        podcast = self.podcast_map.get(podcast_id)

        if not podcast:
            await interaction.response.send_message("Podcast not found.", ephemeral=True)
            return

        report_count = next(
            (r.count for r in self.report_counts if r.podcast_id == podcast_id),
            0
        )

        view = ReportedPodcastActionsView(
            self.api_client, podcast, report_count, parent_view=self
        )
        embed = Embed(
            title=f"🚩 {podcast.title}",
            description=f"**{report_count} dead link reports**\n\n{podcast.description}",
            color=discord.Color.red(),
            url=podcast.url
        )
        embed.add_field(name="Status", value="Archived" if podcast.archived else "Active", inline=True)
        if podcast.image_url:
            embed.set_thumbnail(url=podcast.image_url)

        await interaction.response.edit_message(embed=embed, view=view)

    @button(label="Back to Menu", style=ButtonStyle.secondary, emoji="◀️", row=1)
    async def back_button(self, interaction: Interaction, btn: Button):
        """Go back to podcast menu"""
        view = PodcastMenuView(self.api_client)
        embed = Embed(
            title="Podcast Management",
            description="Choose an action:",
            color=discord.Color.orange()
        )
        await interaction.response.edit_message(embed=embed, view=view)


class ReportedPodcastActionsView(View):
    """Actions for a reported podcast"""

    def __init__(self, api_client, podcast, report_count, parent_view=None, timeout: float = 180):
        super().__init__(timeout=timeout)
        self.api_client = api_client
        self.podcast = podcast
        self.report_count = report_count
        self.parent_view = parent_view

    @button(label="Archive Podcast", style=ButtonStyle.secondary, emoji="🗄️")
    async def archive_button(self, interaction: Interaction, btn: Button):
        """Archive the reported podcast"""
        await interaction.response.defer(ephemeral=True)

        try:
            podcast = await self.api_client.archive_podcast(self.podcast.id)
            self.podcast = podcast

            embed = Embed(
                title="Podcast Archived",
                description=f"**{podcast.title}** has been archived.",
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info(f"User {interaction.user} archived reported podcast: {podcast.title}")

        except Exception as e:
            logger.error(f"Error archiving podcast: {e}", exc_info=True)
            await interaction.followup.send(f"Error: {e}", ephemeral=True)

    @button(label="Clear Reports", style=ButtonStyle.primary, emoji="🧹")
    async def clear_reports_button(self, interaction: Interaction, btn: Button):
        """Clear all reports for this podcast"""
        await interaction.response.defer(ephemeral=True)

        try:
            await self.api_client.clear_podcast_reports(self.podcast.id)

            embed = Embed(
                title="Reports Cleared",
                description=f"All reports for **{self.podcast.title}** have been cleared.",
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info(f"User {interaction.user} cleared reports for: {self.podcast.title}")

        except Exception as e:
            logger.error(f"Error clearing reports: {e}", exc_info=True)
            await interaction.followup.send(f"Error: {e}", ephemeral=True)

    @button(label="Delete Podcast", style=ButtonStyle.danger, emoji="🗑️")
    async def delete_button(self, interaction: Interaction, btn: Button):
        """Delete the podcast"""
        view = ConfirmDeleteView(self.api_client, self.podcast)
        embed = Embed(
            title="Confirm Delete",
            description=f"Are you sure you want to delete **{self.podcast.title}**?\n\nThis action cannot be undone.",
            color=discord.Color.red()
        )
        await interaction.response.edit_message(embed=embed, view=view)

    @button(label="Back", style=ButtonStyle.secondary, emoji="◀️", row=1)
    async def back_button(self, interaction: Interaction, btn: Button):
        """Go back to reports list"""
        try:
            report_counts = await self.api_client.get_link_report_counts()
            podcasts = await self.api_client.get_podcasts(include_archived=True)
            podcast_map = {p.id: p for p in podcasts}

            embed = Embed(
                title="Dead Link Reports",
                description="Podcasts with reported dead links:",
                color=discord.Color.orange()
            )

            for report in sorted(report_counts, key=lambda r: r.count, reverse=True)[:10]:
                podcast = podcast_map.get(report.podcast_id)
                if podcast:
                    status = "🗄️ Archived" if podcast.archived else "✅ Active"
                    embed.add_field(
                        name=f"{podcast.title} ({report.count} reports)",
                        value=f"{status}\n[Link]({podcast.url})",
                        inline=False
                    )

            view = ReportActionsView(self.api_client, report_counts, podcast_map)
            await interaction.response.edit_message(embed=embed, view=view)

        except Exception as e:
            logger.error(f"Error returning to reports: {e}", exc_info=True)
            await interaction.response.send_message(f"Error: {e}", ephemeral=True)
