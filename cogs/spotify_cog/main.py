"""Spotify now-playing command — shows what a user is listening to."""
import colorsys
import logging
import math
from io import BytesIO
from typing import Optional

import aiohttp
import discord
from discord import Color, File, HTTPException, Member, Spotify, app_commands, ui
from discord.ext import commands
from PIL import Image

from base_cog import BaseCog
from cogs.spotify_cog.config import SPOTIFY_EMOJI
from cogs.utils.embeds import red_embed

logger = logging.getLogger(__name__)

DEFAULT_ACCENT = Color.green()


async def _dominant_color(url: str) -> Color:
    """Extract the most eye-catching color from album art, mimicking Spotify.

    Uses Pillow quantize + a scoring formula based on chroma, darkness,
    and cluster dominance (inspired by Spotify's approach).
    """
    try:
        async with aiohttp.ClientSession() as session, session.get(url) as resp:
            if resp.status != 200:
                return DEFAULT_ACCENT
            data = await resp.read()
        img = Image.open(BytesIO(data)).convert("RGB").resize((100, 100))

        # Quantize to 16 color palette
        quantized = img.quantize(colors=16, method=Image.Quantize.MEDIANCUT)
        palette = quantized.getpalette()[:48]  # 16 colors × 3 channels
        hist = quantized.histogram()[:16]
        total_pixels = sum(hist)

        best_score = -1
        best_color = (30, 215, 96)

        for i in range(16):
            r, g, b = palette[i * 3], palette[i * 3 + 1], palette[i * 3 + 2]
            rf, gf, bf = r / 255, g / 255, b / 255

            # Chroma (colorfulness)
            rg = rf - gf
            yb = (rf + gf) / 2 - bf
            chroma = math.sqrt(rg ** 2 + yb ** 2)

            # Darkness (Spotify prefers darker backgrounds for white text)
            lum = math.sqrt(0.299 * rf**2 + 0.587 * gf**2 + 0.114 * bf**2)
            darkness = 1 - lum

            # Dominance (area coverage)
            dominance = hist[i] / total_pixels if total_pixels else 0

            # Spotify-inspired scoring: heavily weight chroma
            score = chroma * 4.92 + darkness * 1.41 + dominance * 0.79

            # Skip near-gray colors (low saturation)
            if chroma < 0.05:
                continue

            if score > best_score:
                best_score = score
                best_color = (r, g, b)

        # Boost saturation in HSV space
        rf, gf, bf = [c / 255 for c in best_color]
        h, s, v = colorsys.rgb_to_hsv(rf, gf, bf)
        s = min(s * 1.4, 1.0)  # boost saturation 40%
        v = min(v, 0.75)  # cap brightness for white text contrast
        rf, gf, bf = colorsys.hsv_to_rgb(h, s, v)
        best_color = (int(rf * 255), int(gf * 255), int(bf * 255))

        return Color.from_rgb(*best_color)
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
                "Make sure you have:\n"
                "• **Display current activity** enabled for this server "
                "(Settings → Activity Privacy)\n"
                "• Spotify linked in **Settings → Connections** with "
                "\"Display Spotify as your status\" on"
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
        """Now playing with rendered Spotify-style card image."""
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
                "Make sure you have:\n"
                "• **Display current activity** enabled for this server "
                "(Settings → Activity Privacy)\n"
                "• Spotify linked in **Settings → Connections** with "
                "\"Display Spotify as your status\" on"
            ))
            return

        # Extract dominant color from album art
        accent = (30, 215, 96)  # Spotify green default
        if spotify.album_cover_url:
            color = await _dominant_color(spotify.album_cover_url)
            accent = (color.r, color.g, color.b)

        from .renderer import render_nowplaying
        buf = await render_nowplaying(
            title=spotify.title or "Unknown",
            artist=spotify.artist or "Unknown",
            album=spotify.album or "",
            album_art_url=spotify.album_cover_url,
            accent=accent,
            listener=target.display_name,
        )

        file = File(buf, filename="nowplaying.png")

        # Send as v2 with Listen button
        try:
            view = discord.ui.LayoutView()
            container_children = [
                discord.ui.MediaGallery(
                    discord.MediaGalleryItem(media="attachment://nowplaying.png"),
                ),
            ]
            if spotify.track_url:
                container_children.append(discord.ui.Separator(visible=True))
                container_children.append(discord.ui.ActionRow(
                    discord.ui.Button(
                        label="Listen on Spotify",
                        url=spotify.track_url,
                        style=discord.ButtonStyle.link,
                        emoji=discord.PartialEmoji.from_str(SPOTIFY_EMOJI),
                    ),
                ))
            view.add_item(discord.ui.Container(*container_children))
            await ctx.send(view=view, file=file)
        except HTTPException:
            # Fallback: just send the image
            buf.seek(0)
            await ctx.send(file=File(buf, filename="nowplaying.png"))


async def setup(bot: commands.Bot):
    await bot.add_cog(SpotifyCog(bot))
