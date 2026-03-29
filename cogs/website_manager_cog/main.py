"""
Website Manager Cog
Provides slash commands for managing website resources (podcasts, videos, etc.)
"""
import logging

import discord
from discord import Embed, Interaction, app_commands
from discord.ext import commands

from base_cog import BaseCog

from .api import WebsiteAPIClient
from .views import MainManageView

logger = logging.getLogger(__name__)

def has_management_permission():
    """Check if user has permission to manage website resources"""
    async def predicate(interaction: Interaction) -> bool:
        # Allow bot owner
        if interaction.user.id == interaction.client.settings.owner_id:
            return True

        # Allow users with manage_messages permission (mods)
        return isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.manage_messages

    return app_commands.check(predicate)

class WebsiteManagerCog(BaseCog):
    """Manage podcasts, videos, and other website resources."""

    def __init__(self, bot: commands.Bot):
        super().__init__(bot)
        self.api_client = WebsiteAPIClient(base_url=bot.settings.website_api_url)

    async def cog_unload(self):
        """Cleanup when cog is unloaded"""
        await self.api_client.close()

    @app_commands.command(name="manage", description="Manage website resources (podcasts, videos, etc.)")
    @app_commands.default_permissions(manage_messages=True)
    @has_management_permission()
    async def manage(self, interaction: Interaction):
        """Open the website management panel"""
        embed = Embed(
            title="Website Management",
            description="Select a resource type to manage:",
            color=discord.Color.blue()
        )
        embed.set_footer(text="This panel is only visible to you")

        view = MainManageView(self.api_client)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        logger.info(f"User {interaction.user} opened website management panel")

    @manage.error
    async def manage_error(self, interaction: Interaction, error: app_commands.AppCommandError):
        """Handle errors for the manage command"""
        if isinstance(error, app_commands.CheckFailure):
            embed = Embed(
                title="Permission Denied",
                description="You don't have permission to manage website resources.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            logger.error(f"Error in manage command: {error}", exc_info=True)
            embed = Embed(
                title="Error",
                description=f"An error occurred: {error!s}",
                color=discord.Color.red()
            )
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(bot):
    """Setup function to add the cog to the bot"""
    await bot.add_cog(WebsiteManagerCog(bot))
    logger.info("WebsiteManagerCog loaded successfully")
