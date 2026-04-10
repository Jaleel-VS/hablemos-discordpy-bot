"""Spotify now-playing command — shows what a user is listening to."""
import logging
from io import BytesIO
from typing import Optional

import aiohttp
import discord
from discord import Color, HTTPException, Member, Spotify, app_commands, ui
from discord.ext import commands
from PIL import Image

from base_cog import BaseCog
from cogs.spotify_cog.config import SPOTIFY_EMOJI
from cogs.utils.embeds import red_embed

logger = logging.getLogger(__name__)

DEFAULT_ACCENT = Color.green()


async def _dominant_color(url: str) -> Color:
    """Fetch an image and return its dominant color, or green on failure."""
    try:
        async with aiohttp.ClientSession() as session, session.get(url) as resp:
            if resp.status != 200:
                return DEFAULT_ACCENT
            data = await resp.read()
        img = Image.open(BytesIO(data)).convert("RGB").resize((1, 1))
        r, g, b = img.getpixel((0, 0))
        return Color.from_rgb(r, g, b)
    except Exception:
        logger.debug("Failed to extract dominant color from %s", url)
        return DEFAULT_ACCENT


class NowPlayingView(ui.LayoutView):
    """Components v2 layout for the now-playing card."""

    def __init__(self, target: Member, spotify: Spotify, accent: Color = DEFAULT_ACCENT):
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
                        emoji=discord.PartialEmoji.from_str(SPOTIFY_EMOJI),
                    ),
                ),
            )

        self.add_item(ui.Container(
            *container_children,
            accent_colour=accent,
        ))


class SpotifyCog(BaseCog):
    """Share what you're listening to on Spotify."""

    async def _send_now_playing(self, ctx: commands.Context, member: Member | None, use_art_color: bool) -> None:
        """Shared logic for now-playing commands."""
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

        accent = DEFAULT_ACCENT
        if use_art_color and spotify.album_cover_url:
            accent = await _dominant_color(spotify.album_cover_url)

        try:
            await ctx.send(view=NowPlayingView(target, spotify, accent))
        except HTTPException:
            logger.exception("Failed to send Spotify view for %s", target)
            await ctx.send(embed=red_embed("Something went wrong sending the embed."))

    @commands.hybrid_command(name="nowplaying", aliases=['spoti', 'np'])
    @commands.cooldown(1, 10, commands.BucketType.user)
    @app_commands.describe(member="The user to check (leave empty for yourself)")
    async def nowplaying(self, ctx: commands.Context, member: Optional[Member] = None):  # noqa: UP045 — discord.py needs Optional[]
        """Shows what song a user is currently listening to on Spotify."""
        await self._send_now_playing(ctx, member, use_art_color=False)

    @commands.command(name="np2")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def nowplaying_v2(self, ctx: commands.Context, member: Optional[Member] = None):  # noqa: UP045 — discord.py needs Optional[]
        """Now playing with album art accent color (experimental)."""
        await self._send_now_playing(ctx, member, use_art_color=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(SpotifyCog(bot))
