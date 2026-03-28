"""Spotify now-playing command — shows what a user is listening to."""
from discord.ext import commands
from discord import app_commands, Embed, Color, HTTPException, Member, Spotify
from base_cog import BaseCog
from cogs.utils.embeds import red_embed
import logging

logger = logging.getLogger(__name__)


class SpotifyCog(BaseCog):

    @commands.hybrid_command(name="nowplaying", aliases=['spoti', 'np'])
    @app_commands.describe(member="The user to check (leave empty for yourself)")
    async def nowplaying(self, ctx: commands.Context, member: Member | None = None):
        """Shows what song a user is currently listening to on Spotify."""
        if ctx.guild is None:
            await ctx.send(embed=red_embed("This command can only be used in a server."))
            return

        target = ctx.guild.get_member((member or ctx.author).id)
        if target is None:
            await ctx.send(embed=red_embed("Could not find that user!"))
            return

        # Find Spotify activity
        spotify = next((a for a in target.activities if isinstance(a, Spotify)), None)

        if not spotify:
            name = "You're" if target.id == ctx.author.id else f"{target.display_name} is"
            await ctx.send(embed=red_embed(
                f"{name} not listening to Spotify right now!\n\n"
                "Make sure you're set to Online and have Spotify linked in "
                "**Settings → Connections**."
            ))
            return

        embed = Embed(
            title=f"{target.display_name} is currently listening to",
            description=f"# {spotify.title}\n**Artist**\n{spotify.artist}",
            color=Color.green(),
        )
        embed.add_field(name="Album", value=spotify.album, inline=True)
        embed.set_author(name=target.display_name, icon_url=target.display_avatar.url)

        if spotify.album_cover_url:
            embed.set_thumbnail(url=spotify.album_cover_url)
        if spotify.track_url:
            embed.add_field(name="Listen on Spotify", value=f"[Click here]({spotify.track_url})", inline=False)

        try:
            await ctx.send(embed=embed)
        except HTTPException:
            logger.exception(f"Failed to send Spotify embed for {target}")
            await ctx.send(embed=red_embed("Something went wrong sending the embed."))


async def setup(bot):
    await bot.add_cog(SpotifyCog(bot))
