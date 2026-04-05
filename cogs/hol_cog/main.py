"""Higher-or-Lower cog — guess which search term is more popular."""
import contextlib
import logging

import discord
from discord import Color, Embed, ui
from discord.ext import commands

from base_cog import BaseCog
from cogs.hol_cog.config import HOL_CHANNEL_IDS
from cogs.hol_cog.data import pick_pair

logger = logging.getLogger(__name__)

TIMEOUT = 30


def _fmt(n: int) -> str:
    return f"{n:,}"


def _round_embed(known: str, known_vol: int, mystery: str, streak: int) -> Embed:
    embed = Embed(color=Color.blurple())
    embed.title = f"🎮 Higher or Lower?  —  Streak: {streak}"
    embed.description = (
        f"**{known}**\n"
        f"🔍 {_fmt(known_vol)} searches/mo\n\n"
        f"**{mystery}**\n"
        f"🔍 ???"
    )
    embed.set_footer(text="Does the second term get more or fewer searches?")
    return embed


def _result_embed(
    known: str, known_vol: int, mystery: str, mystery_vol: int,
    streak: int, result: str,
) -> Embed:
    if result == "correct":
        color = Color.green()
        title = f"✅ Correct!  —  Streak: {streak}"
    elif result == "wrong":
        color = Color.red()
        title = f"💥 Wrong!  —  Final streak: {streak}"
    else:
        color = Color.orange()
        title = f"⏱️ Time's up!  —  Final streak: {streak}"

    embed = Embed(color=color, title=title)
    embed.description = (
        f"**{known}**\n"
        f"🔍 {_fmt(known_vol)} searches/mo\n\n"
        f"**{mystery}**\n"
        f"🔍 {_fmt(mystery_vol)} searches/mo"
    )
    return embed


class GameView(ui.View):
    """Interactive Higher-or-Lower buttons."""

    def __init__(self, cog: "HigherOrLower", player: discord.Member | discord.User):
        super().__init__(timeout=TIMEOUT)
        self.cog = cog
        self.player = player
        self.streak = 0
        self.seen: set[str] = set()
        self.message: discord.Message | None = None
        self.game_over = False

        known, known_vol, mystery, mystery_vol = pick_pair()
        self.known = known
        self.known_vol = known_vol
        self.mystery = mystery
        self.mystery_vol = mystery_vol
        self.seen.update({known, mystery})

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.player.id:
            await interaction.response.send_message("This isn't your game!", ephemeral=True)
            return False
        return True

    async def _handle_guess(self, interaction: discord.Interaction, guessed_higher: bool) -> None:
        actual_higher = self.mystery_vol >= self.known_vol
        correct = guessed_higher == actual_higher

        if correct:
            self.streak += 1

            # Show correct result on current message (no buttons)
            result = _result_embed(
                self.known, self.known_vol, self.mystery, self.mystery_vol,
                self.streak, "correct",
            )
            await interaction.response.edit_message(embed=result, view=None)

            # Chain: mystery becomes the new known
            self.known = self.mystery
            self.known_vol = self.mystery_vol

            try:
                _, _, self.mystery, self.mystery_vol = pick_pair(self.seen)
            except ValueError:
                await interaction.followup.send(
                    f"🏆 You've seen every term! Final streak: **{self.streak}**"
                )
                self._end()
                return

            self.seen.add(self.mystery)

            # Send next round as a new message with fresh buttons
            new_view = GameView(self.cog, self.player)
            new_view.streak = self.streak
            new_view.seen = self.seen
            new_view.known = self.known
            new_view.known_vol = self.known_vol
            new_view.mystery = self.mystery
            new_view.mystery_vol = self.mystery_vol

            embed = _round_embed(self.known, self.known_vol, self.mystery, self.streak)
            msg = await interaction.followup.send(embed=embed, view=new_view, wait=True)
            new_view.message = msg

            # Transfer active game tracking
            self.cog._active[self.player.id] = new_view
            self.stop()
        else:
            result = _result_embed(
                self.known, self.known_vol, self.mystery, self.mystery_vol,
                self.streak, "wrong",
            )
            await interaction.response.edit_message(embed=result, view=None)
            self._end()

    def _end(self) -> None:
        self.game_over = True
        self.cog._active.pop(self.player.id, None)
        self.stop()

    @ui.button(label="🔼 Higher", style=discord.ButtonStyle.green)
    async def higher(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await self._handle_guess(interaction, True)

    @ui.button(label="🔽 Lower", style=discord.ButtonStyle.red)
    async def lower(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await self._handle_guess(interaction, False)

    async def on_timeout(self) -> None:
        if not self.game_over and self.message:
            result = _result_embed(
                self.known, self.known_vol, self.mystery, self.mystery_vol,
                self.streak, "timeout",
            )
            with contextlib.suppress(discord.HTTPException):
                await self.message.edit(embed=result, view=None)
            self._end()


class HigherOrLower(BaseCog):
    """Higher-or-Lower: guess which Google search term is more popular."""

    def __init__(self, bot: commands.Bot):
        super().__init__(bot)
        self._active: dict[int, GameView] = {}

    @commands.command(name="hol")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def hol(self, ctx: commands.Context):
        """Start a Higher-or-Lower game. Guess which search term gets more Google searches!"""
        if HOL_CHANNEL_IDS and ctx.channel.id not in HOL_CHANNEL_IDS and not isinstance(ctx.channel, discord.DMChannel):
            channels = " ".join(f"<#{cid}>" for cid in HOL_CHANNEL_IDS)
            await ctx.send(f"🎮 This game can only be played in {channels} or DMs.")
            return

        if ctx.author.id in self._active:
            await ctx.send("You already have an active game! Finish it first.")
            return

        game = GameView(self, ctx.author)
        self._active[ctx.author.id] = game

        embed = _round_embed(game.known, game.known_vol, game.mystery, 0)
        msg = await ctx.send(embed=embed, view=game)
        game.message = msg


async def setup(bot: commands.Bot):
    await bot.add_cog(HigherOrLower(bot))
