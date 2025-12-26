"""
Vocabulary Notes Cog
Provides slash commands for managing vocabulary notes privately
"""
import discord
from discord.ext import commands
from discord import app_commands, Interaction, Embed
from discord.ui import Modal, TextInput
from base_cog import BaseCog
import logging

logger = logging.getLogger(__name__)


class VocabNoteModal(Modal, title="Add Vocabulary Note"):
    """Modal for adding a vocabulary note"""

    word = TextInput(
        label="Word or Phrase",
        placeholder="e.g., hola, buenos días, etc.",
        required=True,
        max_length=500
    )

    translation = TextInput(
        label="Translation or Definition",
        placeholder="e.g., hello, good morning, etc.",
        required=False,
        max_length=1000,
        style=discord.TextStyle.paragraph
    )

    language = TextInput(
        label="Language (optional)",
        placeholder="e.g., spanish, english, french, etc.",
        required=False,
        max_length=50
    )

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: Interaction):
        """Called when the modal is submitted"""
        try:
            user_id = interaction.user.id
            username = str(interaction.user)

            # Get values from form (convert empty strings to None)
            word_value = self.word.value.strip()
            translation_value = self.translation.value.strip() or None
            language_value = self.language.value.strip().lower() if self.language.value.strip() else None

            # Add to database
            note_id = await self.bot.db.add_vocab_note(
                user_id=user_id,
                username=username,
                word=word_value,
                translation=translation_value,
                language=language_value
            )

            # Get total count
            total_count = await self.bot.db.get_vocab_note_count(user_id)

            # Create success embed
            embed = Embed(
                title="✅ Vocabulary Note Added",
                description=f"**Word:** {word_value}",
                color=discord.Color.green()
            )

            if translation_value:
                embed.add_field(name="Translation", value=translation_value, inline=False)

            if language_value:
                embed.add_field(name="Language", value=language_value.title(), inline=True)

            embed.add_field(name="Note ID", value=str(note_id), inline=True)
            embed.set_footer(text=f"You now have {total_count} vocab notes")

            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.info(f"User {username} ({user_id}) added vocab note: {word_value}")

        except Exception as e:
            logger.error(f"Error adding vocab note: {e}", exc_info=True)
            embed = Embed(
                title="❌ Error",
                description=f"Failed to add vocabulary note: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)


class VocabCog(BaseCog):
    """Cog for managing vocabulary notes with ephemeral messages"""

    def __init__(self, bot: commands.Bot):
        super().__init__(bot)

    vocab_group = app_commands.Group(
        name="vocab",
        description="Manage your vocabulary notes"
    )

    @vocab_group.command(name="add", description="Add a new vocabulary note")
    async def vocab_add(self, interaction: Interaction):
        """Show a form to add a new vocabulary note"""
        # Send the modal (form) to the user
        await interaction.response.send_modal(VocabNoteModal(self.bot))

    @vocab_group.command(name="list", description="View all your vocabulary notes")
    @app_commands.describe(
        limit="Number of notes to show (default: 20, max: 50)"
    )
    async def vocab_list(
        self,
        interaction: Interaction,
        limit: int = 20
    ):
        """List all vocabulary notes (ephemeral)"""
        try:
            user_id = interaction.user.id

            # Validate limit
            if limit < 1 or limit > 50:
                embed = Embed(
                    title="Invalid Limit",
                    description="Limit must be between 1 and 50.",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            # Get notes from database
            notes = await self.bot.db.get_user_vocab_notes(user_id, limit)

            if not notes:
                embed = Embed(
                    title="No Vocabulary Notes",
                    description="You haven't added any vocabulary notes yet!\n\nUse `/vocab add` to create your first note.",
                    color=discord.Color.blue()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            # Create embed with notes
            embed = Embed(
                title=f"Your Vocabulary Notes ({len(notes)} shown)",
                color=discord.Color.blue()
            )

            # Add notes as fields
            for note in notes:
                word = note['word']
                translation = note['translation'] or "No translation"
                language = note['language'] or "N/A"
                note_id = note['id']

                field_value = f"**Translation:** {translation}\n**Language:** {language}\n**ID:** {note_id}"
                embed.add_field(
                    name=f"{word}",
                    value=field_value,
                    inline=False
                )

            total_count = await self.bot.db.get_vocab_note_count(user_id)
            embed.set_footer(text=f"Total vocab notes: {total_count} | Use /vocab delete <id> to remove a note")

            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.info(f"User {interaction.user} ({user_id}) listed {len(notes)} vocab notes")

        except Exception as e:
            logger.error(f"Error listing vocab notes: {e}", exc_info=True)
            embed = Embed(
                title="Error",
                description=f"Failed to list vocabulary notes: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @vocab_group.command(name="search", description="Search your vocabulary notes")
    @app_commands.describe(
        query="Search term (searches both word and translation)"
    )
    async def vocab_search(
        self,
        interaction: Interaction,
        query: str
    ):
        """Search vocabulary notes (ephemeral)"""
        try:
            user_id = interaction.user.id

            # Search notes
            notes = await self.bot.db.search_vocab_notes(user_id, query)

            if not notes:
                embed = Embed(
                    title="No Results",
                    description=f"No vocabulary notes found matching: **{query}**",
                    color=discord.Color.orange()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            # Create embed with search results
            embed = Embed(
                title=f"Search Results for: {query}",
                description=f"Found {len(notes)} matching note(s)",
                color=discord.Color.blue()
            )

            # Add notes as fields
            for note in notes:
                word = note['word']
                translation = note['translation'] or "No translation"
                language = note['language'] or "N/A"
                note_id = note['id']

                field_value = f"**Translation:** {translation}\n**Language:** {language}\n**ID:** {note_id}"
                embed.add_field(
                    name=f"{word}",
                    value=field_value,
                    inline=False
                )

            embed.set_footer(text=f"Use /vocab delete <id> to remove a note")

            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.info(f"User {interaction.user} ({user_id}) searched vocab notes for: {query}")

        except Exception as e:
            logger.error(f"Error searching vocab notes: {e}", exc_info=True)
            embed = Embed(
                title="Error",
                description=f"Failed to search vocabulary notes: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @vocab_group.command(name="delete", description="Delete a vocabulary note")
    @app_commands.describe(
        note_id="The ID of the note to delete"
    )
    async def vocab_delete(
        self,
        interaction: Interaction,
        note_id: int
    ):
        """Delete a vocabulary note (ephemeral)"""
        try:
            user_id = interaction.user.id

            # Delete from database
            deleted = await self.bot.db.delete_vocab_note(note_id, user_id)

            if deleted:
                embed = Embed(
                    title="Note Deleted",
                    description=f"Successfully deleted vocabulary note #{note_id}",
                    color=discord.Color.green()
                )
                logger.info(f"User {interaction.user} ({user_id}) deleted vocab note {note_id}")
            else:
                embed = Embed(
                    title="Not Found",
                    description=f"Could not delete note #{note_id}.\n\nThe note either doesn't exist or doesn't belong to you.",
                    color=discord.Color.red()
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error deleting vocab note: {e}", exc_info=True)
            embed = Embed(
                title="Error",
                description=f"Failed to delete vocabulary note: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    """Setup function to add the cog to the bot"""
    await bot.add_cog(VocabCog(bot))
    logger.info("VocabCog loaded successfully")
