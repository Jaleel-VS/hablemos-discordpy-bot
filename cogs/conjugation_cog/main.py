"""
Conjugation practice cog — interactive Spanish verb conjugation game.
"""
import asyncio
import json
import logging
import random
import unicodedata
from pathlib import Path

import discord
from discord.ext import commands

from base_cog import BaseCog

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 60


def normalize(text: str) -> str:
    """Normalize text for comparison — remove accents, lowercase, strip."""
    if not text:
        return ""
    text = text.strip().lower()
    return ''.join(
        c for c in unicodedata.normalize('NFD', text)
        if unicodedata.category(c) != 'Mn'
    )


PRONOUN_DISPLAY = {
    "él/ella": "él",
    "ellos/ellas": "ellos",
    "él/ella/usted": "él",
    "ellos/ellas/ustedes": "ellos",
}

TENSE_DISPLAY = {
    "presente": "Present",
    "pretérito": "Preterite",
    "futuro": "Future",
}


class ConjugationCog(BaseCog):
    """Interactive Spanish verb conjugation practice."""

    def __init__(self, bot: commands.Bot):
        super().__init__(bot)
        self.active_users: set[int] = set()
        self.verb_data: dict = {}
        self.categories: dict = {}

    async def cog_load(self):
        logger.info("Loading verb data...")
        data_file = Path(__file__).parent / 'verb_data.json'
        with open(data_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.categories = data['categories']
        self.verb_data = data['verbs']
        logger.info(f"Loaded {len(self.verb_data)} verbs across {len(self.categories)} categories")

    @commands.command(name='conj', aliases=['conjugate'])
    async def start_game(self, ctx, category: str = None, questions: int = 10):
        """
        Start a conjugation practice session.

        Usage: $conj [category] [questions]
        Categories: high-frequency, regular-ar, regular-er-ir, irregulars
        """
        if ctx.author.id in self.active_users:
            await ctx.send("You already have an active session. Finish it or type `quit`.")
            return

        # Handle $conj 15 (number as first arg)
        if category and category.isdigit():
            questions = int(category)
            category = "high-frequency"
        category = category or "high-frequency"

        if category not in self.categories:
            cats = ', '.join(f'`{c}`' for c in self.categories)
            await ctx.send(f"Unknown category. Available: {cats}")
            return

        questions = max(1, min(questions, 30))
        cat = self.categories[category]
        verbs = {v: self.verb_data[v] for v in cat['verbs'] if v in self.verb_data}
        tenses = cat['tenses']

        self.active_users.add(ctx.author.id)
        try:
            await self._run_game(ctx, cat['name'], verbs, tenses, questions)
        finally:
            self.active_users.discard(ctx.author.id)

    async def _run_game(self, ctx, category_name: str, verbs: dict,
                        tenses: list[str], total: int):
        """Run the game loop using wait_for."""
        score = 0
        verb_list = list(verbs.keys())
        random.shuffle(verb_list)

        # Welcome
        embed = discord.Embed(
            title="Let's Practice",
            description=f"**{category_name}** — {total} questions",
            color=0x57F287,
        )
        embed.set_footer(text="Type the conjugation or 'quit' to stop")
        await ctx.send(embed=embed)

        for i in range(total):
            # Pick verb, tense, pronoun
            verb_key = verb_list[i % len(verb_list)]
            verb = verbs[verb_key]
            tense = random.choice(tenses)
            pronouns = list(verb['conjugations'][tense].keys())
            pronoun = random.choice(pronouns)
            answer = verb['conjugations'][tense][pronoun]

            display_pronoun = PRONOUN_DISPLAY.get(pronoun, pronoun)
            display_tense = TENSE_DISPLAY.get(tense, tense)

            # Question embed
            q_embed = discord.Embed(
                title=f"Question {i + 1}/{total}",
                description=f"# {display_pronoun} + {verb_key}\n*{verb.get('english', '')}*",
                color=0x5865F2,
            )
            q_embed.add_field(name="Tense", value=display_tense, inline=True)
            if i > 0:
                q_embed.add_field(name="Score", value=f"{score}/{i}", inline=True)
            q_embed.set_footer(text="Type your answer or 'quit'")
            await ctx.send(embed=q_embed)

            # Wait for answer
            def check(m):
                return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id

            try:
                msg = await self.bot.wait_for('message', check=check, timeout=TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                await ctx.send(f"Session timed out. Final score: **{score}/{i}**")
                return

            user_input = msg.content.strip()

            if user_input.lower() in ('quit', 'stop', 'exit'):
                await ctx.send(embed=self._results_embed(score, i, category_name, stopped=True))
                return

            # Check answer (lenient: accept with or without pronoun)
            correct = (
                normalize(user_input) == normalize(answer) or
                normalize(answer) in normalize(user_input)
            )
            if correct:
                score += 1

            # Feedback
            if correct:
                fb = discord.Embed(
                    title="Correct!",
                    description=f"**{display_pronoun} {answer}**",
                    color=0x57F287,
                )
            else:
                fb = discord.Embed(
                    title="Not quite",
                    description=f"You said: **{user_input}**\nAnswer: **{display_pronoun} {answer}**",
                    color=0xED4245,
                )
            fb.add_field(name="Score", value=f"{score}/{i + 1}", inline=True)
            await ctx.send(embed=fb)

        # Game complete
        await ctx.send(embed=self._results_embed(score, total, category_name, stopped=False))

    def _results_embed(self, score: int, answered: int, category: str,
                       stopped: bool) -> discord.Embed:
        if answered == 0:
            desc = "No questions answered."
        else:
            pct = score / answered * 100
            desc = f"Final score: **{score}/{answered}** ({pct:.0f}%)"
            if pct == 100:
                desc += "\n\nPerfecto!"
            elif pct >= 80:
                desc += "\n\nExcelente!"
            elif pct >= 60:
                desc += "\n\nBien hecho!"
            else:
                desc += "\n\nSigue practicando!"

        return discord.Embed(
            title="Practice Stopped" if stopped else "Practice Complete!",
            description=desc,
            color=0xFEE75C if stopped else 0x57F287,
        ).add_field(name="Category", value=category, inline=True)

    @commands.command(name='conj_categories', aliases=['conj_cats'])
    async def show_categories(self, ctx):
        """Show available practice categories."""
        embed = discord.Embed(title="Practice Categories", color=0x5865F2)
        for cat_id, cat in self.categories.items():
            embed.add_field(
                name=cat['name'],
                value=f"*{cat['description']}*\n`{len(cat['verbs'])} verbs` — `$conj {cat_id}`",
                inline=False,
            )
        await ctx.send(embed=embed)

    @commands.command(name='conj_stop')
    async def stop_game(self, ctx):
        """Stop hint — actual stopping is done by typing 'quit' in-game."""
        if ctx.author.id in self.active_users:
            await ctx.send("Type `quit` in the game channel to stop your session.")
        else:
            await ctx.send("You don't have an active session.")


async def setup(bot):
    await bot.add_cog(ConjugationCog(bot))
