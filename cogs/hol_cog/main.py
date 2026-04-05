"""Higher-or-Lower cog — guess which search term is more popular."""
import contextlib
import logging

import discord
from discord import Color, ui
from discord.ext import commands

from base_cog import BaseCog
from cogs.hol_cog.config import HOL_CHANNEL_IDS
from cogs.hol_cog.data import pick_pair

logger = logging.getLogger(__name__)

TIMEOUT = 30
KNOWN_TEXT_ID = 1001
MYSTERY_TEXT_ID = 1002
HEADER_TEXT_ID = 1003


def _fmt(n: int) -> str:
    return f"{n:,}"


class GameView(ui.LayoutView):
    """Interactive Higher-or-Lower game for a single player."""

    def __init__(self, player: discord.Member | discord.User):
        super().__init__(timeout=TIMEOUT)
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

        self._build()

    def _build(self) -> None:
        self.clear_items()
        header = f"### 🎮 Higher or Lower?  Streak: {self.streak}"
        self.add_item(ui.Container(
            ui.TextDisplay(header, id=HEADER_TEXT_ID),
            ui.Separator(visible=True),
            ui.TextDisplay(
                f"**{self.known}**\n🔍 {_fmt(self.known_vol)} searches/mo",
                id=KNOWN_TEXT_ID,
            ),
            ui.Separator(visible=False),
            ui.TextDisplay(f"**{self.mystery}**\n🔍 ???", id=MYSTERY_TEXT_ID),
            ui.Separator(visible=True),
            self.buttons,
            accent_colour=Color.blurple(),
        ))

    buttons = ui.ActionRow()

    @buttons.button(label="🔼 Higher", style=discord.ButtonStyle.green)
    async def higher(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await self._handle_guess(interaction, True)

    @buttons.button(label="🔽 Lower", style=discord.ButtonStyle.red)
    async def lower(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await self._handle_guess(interaction, False)

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
            # Chain: mystery becomes the new known
            self.known = self.mystery
            self.known_vol = self.mystery_vol

            try:
                _, _, self.mystery, self.mystery_vol = pick_pair(self.seen)
            except ValueError:
                # Ran out of terms
                self._show_end("🏆 You've seen every term!")
                await interaction.response.edit_message(view=self)
                self.game_over = True
                self.stop()
                return

            self.seen.add(self.mystery)
            self._build()
            await interaction.response.edit_message(view=self)
        else:
            self._show_end("💥 Wrong!")
            await interaction.response.edit_message(view=self)
            self.game_over = True
            self.stop()

    def _show_end(self, reason: str) -> None:
        """Replace the view with a game-over screen."""
        self.clear_items()
        self.add_item(ui.Container(
            ui.TextDisplay(f"### {reason}  Final streak: {self.streak}"),
            ui.Separator(visible=True),
            ui.TextDisplay(
                f"**{self.known}**\n🔍 {_fmt(self.known_vol)} searches/mo"
            ),
            ui.Separator(visible=False),
            ui.TextDisplay(
                f"**{self.mystery}**\n🔍 {_fmt(self.mystery_vol)} searches/mo"
            ),
            accent_colour=Color.red(),
        ))

    async def on_timeout(self) -> None:
        if not self.game_over and self.message:
            self._show_end("⏱️ Time's up!")
            with contextlib.suppress(discord.HTTPException):
                await self.message.edit(view=self)


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
            await ctx.send("🎮 This game can only be played in designated channels or DMs.")
            return

        if ctx.author.id in self._active:
            await ctx.send("You already have an active game! Finish it first.")
            return

        game = GameView(ctx.author)
        self._active[ctx.author.id] = game

        msg = await ctx.send(view=game)
        game.message = msg

        await game.wait()
        self._active.pop(ctx.author.id, None)


async def setup(bot: commands.Bot):
    await bot.add_cog(HigherOrLower(bot))
