"""Practice UI test cog — prototype LayoutView-based practice flow."""
import logging
import random

import discord
from discord import Color, ui
from discord.ext import commands

from base_cog import BaseCog

logger = logging.getLogger(__name__)

# Fake card data for testing
SAMPLE_CARDS = [
    {"sentence_with_blank": "El ___ está lleno de agua.", "sentence_translation": "The glass is full of water.", "word": "vaso", "translation": "glass", "level": "A"},
    {"sentence_with_blank": "Quiero ___ un vaso de agua, por favor.", "sentence_translation": "I want a glass of water, please.", "word": "beber", "translation": "to drink", "level": "A"},
    {"sentence_with_blank": "La ___ económica del país es complicada.", "sentence_translation": "The economic situation of the country is complicated.", "word": "situación", "translation": "situation", "level": "B"},
    {"sentence_with_blank": "No se puede ___ la economía de las decisiones políticas.", "sentence_translation": "You cannot dissociate the economy from political decisions.", "word": "desvincular", "translation": "to dissociate", "level": "C"},
]


class QuestionView(ui.LayoutView):
    """A single practice question using Components V2."""

    def __init__(self, card: dict, card_index: int, total: int):
        super().__init__(timeout=120)
        self.card = card
        self.card_index = card_index
        self.total = total

        # Distractors
        other_words = [c["word"] for c in SAMPLE_CARDS if c["word"] != card["word"]]
        choices = [*random.sample(other_words, min(3, len(other_words))), card["word"]]
        random.shuffle(choices)

        # Build layout
        row = ui.ActionRow()
        for choice in choices:
            btn = ui.Button(label=choice, style=discord.ButtonStyle.primary)
            btn.callback = self._make_callback(choice)
            row.add_item(btn)

        control_row = ui.ActionRow()
        quit_btn = ui.Button(label="Quit", style=discord.ButtonStyle.danger)
        quit_btn.callback = self._quit
        control_row.add_item(quit_btn)

        self.add_item(ui.Container(
            ui.TextDisplay(f"## Practice ({card_index + 1}/{total})"),
            ui.TextDisplay(f"**{card['sentence_with_blank']}**"),
            ui.Separator(visible=True),
            ui.TextDisplay(f"-# *{card['sentence_translation']}*"),
            row,
            control_row,
            accent_colour=Color.blue(),
        ))

    def _make_callback(self, choice: str):
        async def callback(interaction: discord.Interaction):
            correct = choice == self.card["word"]
            await interaction.response.edit_message(
                view=ResultView(self.card, choice, correct, self.card_index, self.total)
            )
        return callback

    async def _quit(self, interaction: discord.Interaction):
        done = ui.LayoutView()
        done.add_item(ui.Container(
            ui.TextDisplay("## Session Ended"),
            ui.TextDisplay("Quit early. No worries!"),
            accent_colour=Color.orange(),
        ))
        await interaction.response.edit_message(view=done)


class ResultView(ui.LayoutView):
    """Shows the result of an answer."""

    def __init__(self, card: dict, answer: str, correct: bool, card_index: int, total: int):
        super().__init__(timeout=120)
        self.card = card
        self.card_index = card_index
        self.total = total

        if correct:
            title = "## ✅ Correct!"
            colour = Color.green()
        else:
            title = "## ❌ Not quite"
            colour = Color.red()

        highlighted = card["sentence_with_blank"].replace("___", f"**{card['word']}**")

        parts = [
            ui.TextDisplay(title),
            ui.TextDisplay(highlighted),
            ui.Separator(visible=True),
            ui.TextDisplay(f"**{card['word']}** — {card['translation']}"),
            ui.TextDisplay(f"-# *{card['sentence_translation']}*"),
        ]

        if not correct:
            parts.insert(2, ui.TextDisplay(f"Your answer: ~~{answer}~~"))

        # Next button
        row = ui.ActionRow()
        if card_index + 1 < total:
            next_btn = ui.Button(label="Next", style=discord.ButtonStyle.primary)
            next_btn.callback = self._next
            row.add_item(next_btn)
        else:
            done_btn = ui.Button(label="Done", style=discord.ButtonStyle.success)
            done_btn.callback = self._done
            row.add_item(done_btn)

        parts.append(row)
        self.add_item(ui.Container(*parts, accent_colour=colour))

    async def _next(self, interaction: discord.Interaction):
        next_card = SAMPLE_CARDS[(self.card_index + 1) % len(SAMPLE_CARDS)]
        await interaction.response.edit_message(
            view=QuestionView(next_card, self.card_index + 1, self.total)
        )

    async def _done(self, interaction: discord.Interaction):
        done = ui.LayoutView()
        done.add_item(ui.Container(
            ui.TextDisplay("## 🎉 Session Complete!"),
            ui.TextDisplay(f"Reviewed {self.total} cards."),
            accent_colour=Color.gold(),
        ))
        await interaction.response.edit_message(view=done)


class StartView(ui.View):
    """Initial view with a button to start the ephemeral practice flow."""

    @ui.button(label="Start Practice", style=discord.ButtonStyle.green)
    async def start(self, interaction: discord.Interaction, button: ui.Button):
        cards = SAMPLE_CARDS[:4]
        await interaction.response.send_message(
            view=QuestionView(cards[0], 0, len(cards)),
            ephemeral=True,
        )


class PracticeTestCog(BaseCog):
    """Temporary test cog for LayoutView practice UI."""

    @commands.command(name="pt")
    async def practice_test(self, ctx: commands.Context):
        """Test the new practice UI. Click the button to start."""
        await ctx.send("Practice UI test:", view=StartView())


async def setup(bot):
    await bot.add_cog(PracticeTestCog(bot))
