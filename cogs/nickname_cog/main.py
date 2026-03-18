import logging
import discord
from discord import app_commands, Interaction, Embed
from discord.ext import commands, tasks

from base_cog import BaseCog

logger = logging.getLogger(__name__)

MAX_NICKNAMES = 10
MAX_NICK_LENGTH = 32


class NicknameCog(BaseCog):
    """Rotates user nicknames from a personal list every 30 minutes."""

    nickname_group = app_commands.Group(
        name="nickname",
        description="Manage your rotating nickname list"
    )

    def __init__(self, bot: commands.Bot):
        super().__init__(bot)

    async def cog_load(self):
        self.rotate_nicknames.start()

    async def cog_unload(self):
        self.rotate_nicknames.cancel()

    # ── Background Task ──────────────────────────────────────────────

    @tasks.loop(minutes=30)
    async def rotate_nicknames(self):
        try:
            rows = await self.bot.db.get_all_nickname_rotations()
            for row in rows:
                guild = self.bot.get_guild(row['guild_id'])
                if not guild:
                    continue
                member = guild.get_member(row['user_id'])
                if not member:
                    continue

                nicknames = row['nicknames']
                if not nicknames:
                    continue

                next_index = (row['current_index'] + 1) % len(nicknames)
                try:
                    await member.edit(nick=nicknames[next_index])
                    await self.bot.db.advance_nickname_index(guild.id, member.id, next_index)
                except discord.Forbidden:
                    logger.warning(f"Cannot rename {member} in {guild} — missing permissions or role hierarchy")
                except Exception as e:
                    logger.error(f"Error rotating nickname for {member} in {guild}: {e}")
        except Exception as e:
            logger.error(f"Error in rotate_nicknames task: {e}")

    @rotate_nicknames.before_loop
    async def before_rotate(self):
        await self.bot.wait_until_ready()

    # ── Commands ─────────────────────────────────────────────────────

    @nickname_group.command(name="add", description="Add a nickname to your rotation list")
    @app_commands.describe(name="The nickname to add (max 32 characters)")
    async def nickname_add(self, interaction: Interaction, name: str):
        name = name.strip()
        if not name or len(name) > MAX_NICK_LENGTH:
            await interaction.response.send_message(
                embed=Embed(description=f"Nickname must be 1-{MAX_NICK_LENGTH} characters.", color=discord.Color.red()),
                ephemeral=True
            )
            return

        nicknames = await self.bot.db.get_nicknames(interaction.guild_id, interaction.user.id)

        if len(nicknames) >= MAX_NICKNAMES:
            await interaction.response.send_message(
                embed=Embed(description=f"You already have {MAX_NICKNAMES} nicknames. Remove one first.", color=discord.Color.red()),
                ephemeral=True
            )
            return

        if name in nicknames:
            await interaction.response.send_message(
                embed=Embed(description="That nickname is already in your list.", color=discord.Color.red()),
                ephemeral=True
            )
            return

        await self.bot.db.add_nickname(interaction.guild_id, interaction.user.id, name)
        count = len(nicknames) + 1
        await interaction.response.send_message(
            embed=Embed(
                title="Nickname Added ✅",
                description=f"**{name}** added to your rotation list ({count}/{MAX_NICKNAMES}).",
                color=discord.Color.green()
            ),
            ephemeral=True
        )
        logger.info(f"{interaction.user} added nickname '{name}' in {interaction.guild}")

    @nickname_group.command(name="remove", description="Remove a nickname from your rotation list")
    @app_commands.describe(name="The nickname to remove")
    async def nickname_remove(self, interaction: Interaction, name: str):
        name = name.strip()
        nicknames = await self.bot.db.get_nicknames(interaction.guild_id, interaction.user.id)

        if name not in nicknames:
            await interaction.response.send_message(
                embed=Embed(description="That nickname isn't in your list.", color=discord.Color.red()),
                ephemeral=True
            )
            return

        await self.bot.db.remove_nickname(interaction.guild_id, interaction.user.id, name)
        await interaction.response.send_message(
            embed=Embed(
                title="Nickname Removed 🗑️",
                description=f"**{name}** removed from your rotation list.",
                color=discord.Color.green()
            ),
            ephemeral=True
        )
        logger.info(f"{interaction.user} removed nickname '{name}' in {interaction.guild}")

    @nickname_group.command(name="list", description="View your current nickname rotation list")
    async def nickname_list(self, interaction: Interaction):
        nicknames = await self.bot.db.get_nicknames(interaction.guild_id, interaction.user.id)

        if not nicknames:
            await interaction.response.send_message(
                embed=Embed(
                    description="Your rotation list is empty. Use `/nickname add` to get started.",
                    color=discord.Color.blue()
                ),
                ephemeral=True
            )
            return

        current_index = await self.bot.db.get_nickname_index(interaction.guild_id, interaction.user.id)
        lines = []
        for i, nick in enumerate(nicknames):
            marker = " ◀️" if i == current_index else ""
            lines.append(f"`{i + 1}.` {nick}{marker}")

        await interaction.response.send_message(
            embed=Embed(
                title=f"Your Nickname Rotation ({len(nicknames)}/{MAX_NICKNAMES})",
                description="\n".join(lines),
                color=discord.Color.blue()
            ).set_footer(text="◀️ = current nickname"),
            ephemeral=True
        )

    @nickname_group.command(name="optout", description="Clear your list and stop nickname rotation")
    async def nickname_optout(self, interaction: Interaction):
        nicknames = await self.bot.db.get_nicknames(interaction.guild_id, interaction.user.id)

        if not nicknames:
            await interaction.response.send_message(
                embed=Embed(description="You don't have any nicknames set.", color=discord.Color.orange()),
                ephemeral=True
            )
            return

        await self.bot.db.clear_nicknames(interaction.guild_id, interaction.user.id)
        await interaction.response.send_message(
            embed=Embed(
                title="Nickname Rotation Stopped 🛑",
                description="Your nickname list has been cleared and rotation stopped.",
                color=discord.Color.green()
            ),
            ephemeral=True
        )
        logger.info(f"{interaction.user} opted out of nickname rotation in {interaction.guild}")


async def setup(bot):
    await bot.add_cog(NicknameCog(bot))
