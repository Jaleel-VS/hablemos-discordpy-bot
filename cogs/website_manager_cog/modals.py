"""
Discord modals (forms) for website management
"""
import discord
from discord import Interaction, Embed
from discord.ui import Modal, TextInput, Select
import logging

logger = logging.getLogger(__name__)


class AddPodcastModal(Modal, title="Add New Podcast"):
    """Modal for adding a new podcast"""

    podcast_title = TextInput(
        label="Title",
        placeholder="e.g., Coffee Break Spanish",
        required=True,
        max_length=255
    )

    description = TextInput(
        label="Description",
        placeholder="Brief description of the podcast...",
        required=True,
        max_length=1000,
        style=discord.TextStyle.paragraph
    )

    url = TextInput(
        label="Podcast URL",
        placeholder="https://example.com/podcast",
        required=True,
        max_length=500
    )

    image_url = TextInput(
        label="Image URL",
        placeholder="https://example.com/image.jpg",
        required=True,
        max_length=500
    )

    def __init__(self, api_client, on_success_callback=None):
        super().__init__()
        self.api_client = api_client
        self.on_success_callback = on_success_callback
        # Store additional fields to be set via a follow-up
        self.language = 'es'
        self.level = 'intermediate'
        self.country = 'Various'
        self.topic = 'General Learning'

    async def on_submit(self, interaction: Interaction):
        """Called when the modal is submitted"""
        try:
            # Defer since API call might take a moment
            await interaction.response.defer(ephemeral=True)

            podcast = await self.api_client.create_podcast(
                title=self.podcast_title.value.strip(),
                description=self.description.value.strip(),
                url=self.url.value.strip(),
                image_url=self.image_url.value.strip(),
                language=self.language,
                level=self.level,
                country=self.country,
                topic=self.topic
            )

            embed = Embed(
                title="Podcast Added",
                description=f"**{podcast.title}** has been added successfully!",
                color=discord.Color.green()
            )
            embed.add_field(name="Language", value=podcast.language.upper(), inline=True)
            embed.add_field(name="Level", value=podcast.level.title(), inline=True)
            embed.add_field(name="Country", value=podcast.country, inline=True)
            embed.set_thumbnail(url=podcast.image_url)

            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info(f"User {interaction.user} added podcast: {podcast.title}")

            if self.on_success_callback:
                await self.on_success_callback()

        except Exception as e:
            logger.error(f"Error adding podcast: {e}", exc_info=True)
            embed = Embed(
                title="Error",
                description=f"Failed to add podcast: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)


class AddPodcastModalFull(Modal, title="Add New Podcast"):
    """Full modal for adding a podcast with all fields (uses 2 modals due to Discord's 5 field limit)"""

    podcast_title = TextInput(
        label="Title",
        placeholder="e.g., Coffee Break Spanish",
        required=True,
        max_length=255
    )

    description = TextInput(
        label="Description",
        placeholder="Brief description of the podcast...",
        required=True,
        max_length=1000,
        style=discord.TextStyle.paragraph
    )

    url = TextInput(
        label="Podcast URL",
        placeholder="https://example.com/podcast",
        required=True,
        max_length=500
    )

    image_url = TextInput(
        label="Image URL",
        placeholder="https://example.com/image.jpg",
        required=True,
        max_length=500
    )

    metadata = TextInput(
        label="Language, Level, Country, Topic (comma-separated)",
        placeholder="es, intermediate, Spain, Grammar",
        required=True,
        max_length=200
    )

    def __init__(self, api_client, on_success_callback=None):
        super().__init__()
        self.api_client = api_client
        self.on_success_callback = on_success_callback

    async def on_submit(self, interaction: Interaction):
        """Called when the modal is submitted"""
        try:
            await interaction.response.defer(ephemeral=True)

            # Parse metadata field
            metadata_parts = [p.strip() for p in self.metadata.value.split(',')]
            if len(metadata_parts) < 4:
                raise ValueError("Please provide all 4 values: language, level, country, topic")

            language = metadata_parts[0].lower()
            if language not in ('en', 'es', 'both'):
                raise ValueError("Language must be 'en', 'es', or 'both'")

            level = metadata_parts[1].lower()
            if level not in ('beginner', 'intermediate', 'advanced'):
                raise ValueError("Level must be 'beginner', 'intermediate', or 'advanced'")

            country = metadata_parts[2]
            topic = metadata_parts[3]

            podcast = await self.api_client.create_podcast(
                title=self.podcast_title.value.strip(),
                description=self.description.value.strip(),
                url=self.url.value.strip(),
                image_url=self.image_url.value.strip(),
                language=language,
                level=level,
                country=country,
                topic=topic
            )

            embed = Embed(
                title="Podcast Added",
                description=f"**{podcast.title}** has been added successfully!",
                color=discord.Color.green()
            )
            embed.add_field(name="Language", value=podcast.language.upper(), inline=True)
            embed.add_field(name="Level", value=podcast.level.title(), inline=True)
            embed.add_field(name="Country", value=podcast.country, inline=True)
            embed.add_field(name="Topic", value=podcast.topic, inline=True)
            if podcast.image_url:
                embed.set_thumbnail(url=podcast.image_url)

            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info(f"User {interaction.user} added podcast: {podcast.title}")

            if self.on_success_callback:
                await self.on_success_callback()

        except ValueError as e:
            embed = Embed(
                title="Validation Error",
                description=str(e),
                color=discord.Color.orange()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Error adding podcast: {e}", exc_info=True)
            embed = Embed(
                title="Error",
                description=f"Failed to add podcast: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)


class EditPodcastModal(Modal, title="Edit Podcast"):
    """Modal for editing an existing podcast"""

    podcast_title = TextInput(
        label="Title",
        required=True,
        max_length=255
    )

    description = TextInput(
        label="Description",
        required=True,
        max_length=1000,
        style=discord.TextStyle.paragraph
    )

    url = TextInput(
        label="Podcast URL",
        required=True,
        max_length=500
    )

    image_url = TextInput(
        label="Image URL",
        required=True,
        max_length=500
    )

    metadata = TextInput(
        label="Language, Level, Country, Topic (comma-separated)",
        required=True,
        max_length=200
    )

    def __init__(self, api_client, podcast, on_success_callback=None):
        super().__init__()
        self.api_client = api_client
        self.podcast = podcast
        self.on_success_callback = on_success_callback

        # Pre-fill with existing values
        self.podcast_title.default = podcast.title
        self.description.default = podcast.description
        self.url.default = podcast.url
        self.image_url.default = podcast.image_url
        self.metadata.default = f"{podcast.language}, {podcast.level}, {podcast.country}, {podcast.topic}"

    async def on_submit(self, interaction: Interaction):
        """Called when the modal is submitted"""
        try:
            await interaction.response.defer(ephemeral=True)

            # Parse metadata field
            metadata_parts = [p.strip() for p in self.metadata.value.split(',')]
            if len(metadata_parts) < 4:
                raise ValueError("Please provide all 4 values: language, level, country, topic")

            language = metadata_parts[0].lower()
            if language not in ('en', 'es', 'both'):
                raise ValueError("Language must be 'en', 'es', or 'both'")

            level = metadata_parts[1].lower()
            if level not in ('beginner', 'intermediate', 'advanced'):
                raise ValueError("Level must be 'beginner', 'intermediate', or 'advanced'")

            country = metadata_parts[2]
            topic = metadata_parts[3]

            podcast = await self.api_client.update_podcast(
                self.podcast.id,
                title=self.podcast_title.value.strip(),
                description=self.description.value.strip(),
                url=self.url.value.strip(),
                image_url=self.image_url.value.strip(),
                language=language,
                level=level,
                country=country,
                topic=topic
            )

            embed = Embed(
                title="Podcast Updated",
                description=f"**{podcast.title}** has been updated!",
                color=discord.Color.green()
            )
            if podcast.image_url:
                embed.set_thumbnail(url=podcast.image_url)

            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info(f"User {interaction.user} updated podcast: {podcast.title}")

            if self.on_success_callback:
                await self.on_success_callback()

        except ValueError as e:
            embed = Embed(
                title="Validation Error",
                description=str(e),
                color=discord.Color.orange()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Error updating podcast: {e}", exc_info=True)
            embed = Embed(
                title="Error",
                description=f"Failed to update podcast: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
