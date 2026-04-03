"""Spotify now-playing command — shows what a user is listening to."""
import logging

import discord
from discord import Color, HTTPException, Member, Spotify, app_commands, ui
from discord.ext import commands

from base_cog import BaseCog
from cogs.utils.embeds import red_embed

logger = logging.getLogger(__name__)


class NowPlayingView(ui.LayoutView):
    """Components v2 layout for the now-playing card."""

    def __init__(self, target: Member, spotify: Spotify):
        super().__init__()

        lines = [
            f"### 🎵 {spotify.title}",
            f"**{spotify.artist}**",
            f"-# {spotify.album}",
        ]

        container_children = [
            ui.Section(
                ui.TextDisplay(
                    f"-# {target.display_name} is listening to\n" + "\n".join(lines),
                ),
                accessory=ui.Thumbnail(
                    spotify.album_cover_url or target.display_avatar.url,
                ),
            ),
        ]

        if spotify.track_url:
            container_children.append(ui.Separator(visible=True))
            container_children.append(
                ui.ActionRow(
                    ui.Button(
                        label="Listen on Spotify",
                        url=spotify.track_url,
                        style=discord.ButtonStyle.link,
                        emoji="🎧",
                    ),
                ),
            )

        self.add_item(ui.Container(
            *container_children,
            accent_colour=Color.green(),
        ))


class SpotifyCog(BaseCog):
    """Share what you're listening to on Spotify."""

    @commands.hybrid_command(name="nowplaying", aliases=['spoti', 'np'])
    @commands.cooldown(1, 10, commands.BucketType.user)
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

        spotify = next((a for a in target.activities if isinstance(a, Spotify)), None)

        if not spotify:
            name = "You're" if target.id == ctx.author.id else f"{target.display_name} is"
            await ctx.send(embed=red_embed(
                f"{name} not listening to Spotify right now!\n\n"
                "Make sure you're set to Online and have Spotify linked in "
                "**Settings → Connections**."
            ))
            return

        try:
            await ctx.send(view=NowPlayingView(target, spotify))
        except HTTPException:
            logger.exception("Failed to send Spotify view for %s", target)
            await ctx.send(embed=red_embed("Something went wrong sending the embed."))


async def setup(bot):
    await bot.add_cog(SpotifyCog(bot))
