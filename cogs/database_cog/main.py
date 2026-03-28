import logging

from discord import Color, Embed
from discord.ext.commands import Bot, command, is_owner

from base_cog import BaseCog
from cogs.utils.embeds import blue_embed, green_embed, red_embed

logger = logging.getLogger(__name__)


class DatabaseCommands(BaseCog):
    def __init__(self, bot: Bot):
        super().__init__(bot)

    @command(aliases=['addnote'])
    @is_owner()
    async def note(self, ctx, *, content: str):
        """
        Add a note to the database
        Usage: !note <your note content>
        """
        try:
            user_id = ctx.author.id
            username = str(ctx.author)

            note_id = await self.bot.db.add_note(user_id, username, content)

            embed = green_embed(
                f"Note saved successfully!\n"
                f"**Note ID:** {note_id}\n"
                f"**Content:** {content}"
            )
            await ctx.send(embed=embed)
            logger.info(f"Note {note_id} created by {username} ({user_id})")

        except Exception as e:
            logger.error(f"Error adding note: {e}")
            await ctx.send(embed=red_embed(f"Failed to save note: {e!s}"))

    @command(aliases=['getnote', 'readnote'])
    @is_owner()
    async def shownote(self, ctx, note_id: int):
        """
        Get a specific note by ID
        Usage: !shownote <note_id>
        """
        try:
            note = await self.bot.db.get_note(note_id)

            if note is None:
                await ctx.send(embed=red_embed(f"Note with ID {note_id} not found."))
                return

            embed = blue_embed(
                f"**Note ID:** {note['id']}\n"
                f"**Author:** {note['username']}\n"
                f"**Content:** {note['content']}\n"
                f"**Created:** {note['created_at'].strftime('%Y-%m-%d %H:%M:%S')}"
            )
            embed.set_author(name=f"Note by {note['username']}")
            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Error retrieving note: {e}")
            await ctx.send(embed=red_embed(f"Failed to retrieve note: {e!s}"))

    @command(aliases=['mynotes', 'listnotes'])
    @is_owner()
    async def notes(self, ctx, limit: int = 5):
        """
        List your recent notes
        Usage: !notes [limit]
        """
        try:
            user_id = ctx.author.id

            if limit < 1 or limit > 20:
                await ctx.send(embed=red_embed("Limit must be between 1 and 20."))
                return

            notes = await self.bot.db.get_user_notes(user_id, limit)

            if not notes:
                await ctx.send(embed=blue_embed("You don't have any notes yet. Use `!note <content>` to create one!"))
                return

            description = ""
            for note in notes:
                description += f"**ID {note['id']}:** {note['content'][:50]}{'...' if len(note['content']) > 50 else ''}\n"

            embed = Embed(
                title=f"Your Notes ({len(notes)} most recent)",
                description=description,
                color=Color(int('3498db', 16))
            )
            embed.set_footer(text="Use !shownote <id> to view full note")
            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Error listing notes: {e}")
            await ctx.send(embed=red_embed(f"Failed to list notes: {e!s}"))

    @command(aliases=['delnote', 'removenote'])
    @is_owner()
    async def deletenote(self, ctx, note_id: int):
        """
        Delete one of your notes
        Usage: !deletenote <note_id>
        """
        try:
            user_id = ctx.author.id

            deleted = await self.bot.db.delete_note(note_id, user_id)

            if deleted:
                await ctx.send(embed=green_embed(f"Note {note_id} deleted successfully!"))
                logger.info(f"Note {note_id} deleted by user {user_id}")
            else:
                await ctx.send(embed=red_embed(f"Could not delete note {note_id}. Either it doesn't exist or you don't own it."))

        except Exception as e:
            logger.error(f"Error deleting note: {e}")
            await ctx.send(embed=red_embed(f"Failed to delete note: {e!s}"))

async def setup(bot):
    await bot.add_cog(DatabaseCommands(bot))
