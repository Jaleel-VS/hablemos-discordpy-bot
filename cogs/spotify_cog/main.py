from discord.ext.commands import command, Bot
from base_cog import BaseCog
from discord import Embed, Color, Member, Spotify
from typing import Optional
import logging


class SpotifyCog(BaseCog):
    def __init__(self, bot: Bot):
        super().__init__(bot)

    @command(aliases=['spotify', 'song', 'music'])
    async def nowplaying(self, ctx, member: Optional[Member] = None):
        """
        Shows what song a user is currently listening to on Spotify
        Usage: !nowplaying [@user]
        If no user is mentioned, shows your current song
        """
        logging.info(f"nowplaying command called by {ctx.author} for member: {member}")

        # Fetch the member from the guild to get full presence data
        if member is None:
            target = ctx.guild.get_member(ctx.author.id)
            logging.debug(f"Fetched member from guild: {target}")
        else:
            target = member
            logging.debug(f"Using provided member: {target}")

        if target is None:
            logging.warning(f"Could not find member in guild: {ctx.author.id}")
            await ctx.send(embed=Embed(
                description="Could not find that user!",
                color=Color.red()
            ))
            return

        # Find Spotify activity
        logging.debug(f"Checking activities for {target.display_name}: {[type(a).__name__ for a in target.activities]}")
        spotify_activity = None
        for activity in target.activities:
            if isinstance(activity, Spotify):
                spotify_activity = activity
                logging.info(f"Found Spotify activity for {target.display_name}: {activity.title} by {activity.artist}")
                break

        if not spotify_activity:
            logging.info(f"No Spotify activity found for {target.display_name}")
            if target == ctx.author:
                await ctx.send(embed=Embed(
                    description="You're not listening to Spotify right now!",
                    color=Color.red()
                ))
            else:
                await ctx.send(embed=Embed(
                    description=f"{target.display_name} is not listening to Spotify right now!",
                    color=Color.red()
                ))
            return

        # Create embed with song information
        embed = Embed(
            title=f"{target.display_name} is currently listening to",
            description=f"**{spotify_activity.title}**",
            color=Color.green()
        )

        # Add song details
        embed.add_field(name="Artist", value=spotify_activity.artist, inline=True)
        embed.add_field(name="Album", value=spotify_activity.album, inline=True)

        # Calculate song duration and current position
        duration = spotify_activity.duration
        position = (ctx.message.created_at - spotify_activity.start).total_seconds()

        # Format time as MM:SS
        def format_time(seconds):
            mins = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{mins}:{secs:02d}"

        progress = f"{format_time(position)} / {format_time(duration.total_seconds())}"
        embed.add_field(name="Progress", value=progress, inline=False)

        # Add album artwork as thumbnail
        if spotify_activity.album_cover_url:
            embed.set_thumbnail(url=spotify_activity.album_cover_url)

        # Add user info
        embed.set_author(name=target.display_name, icon_url=target.display_avatar.url)

        # Add track URL
        embed.add_field(name="Listen on Spotify", value=f"[Click here]({spotify_activity.track_url})", inline=False)

        logging.info(f"Successfully sending Spotify embed for {target.display_name}")
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(SpotifyCog(bot))
