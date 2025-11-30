"""
Simplified conjugation practice cog - UX focused
Clean, simple, effective learning experience
"""

import json
import logging
import random
import unicodedata
from pathlib import Path
from typing import Dict, Optional

import discord
from discord.ext import commands

from base_cog import BaseCog

logger = logging.getLogger(__name__)


def normalize_answer(text: str) -> str:
    """Normalize text for comparison - remove accents, lowercase, strip whitespace"""
    if not text:
        return ""
    text = text.strip().lower()
    # Remove accents
    return ''.join(
        c for c in unicodedata.normalize('NFD', text)
        if unicodedata.category(c) != 'Mn'
    )


def simplify_pronoun(pronoun: str) -> str:
    """Simplify pronoun display for less confusion"""
    simplifications = {
        "él/ella": "él",
        "ellos/ellas": "ellos",
        "él/ella/usted": "él",
        "ellos/ellas/ustedes": "ellos"
    }
    return simplifications.get(pronoun, pronoun)


class GameSession:
    """Simple game session state"""

    def __init__(self, user_id: int, channel_id: int, category: str,
                 category_data: dict, verb_data: dict, total_questions: int = 10):
        self.user_id = user_id
        self.channel_id = channel_id
        self.category = category
        self.category_name = category_data['name']
        self.available_verbs = category_data['verbs'].copy()
        self.available_tenses = category_data['tenses'].copy()
        self.verb_data = verb_data
        self.total_questions = total_questions
        self.questions_answered = 0
        self.score = 0
        self.current_question = None

        # Shuffle verbs for variety
        random.shuffle(self.available_verbs)

    def generate_question(self) -> Optional[dict]:
        """Generate a new question"""
        if self.questions_answered >= self.total_questions:
            return None

        # Pick a random verb from available
        if not self.available_verbs:
            # Refill if we run out
            self.available_verbs = list(self.verb_data.keys())
            random.shuffle(self.available_verbs)

        verb = random.choice(self.available_verbs)
        verb_info = self.verb_data[verb]

        # Pick a random tense
        tense = random.choice(self.available_tenses)

        # Pick a random pronoun
        pronouns = list(verb_info['conjugations'][tense].keys())
        pronoun = random.choice(pronouns)

        self.current_question = {
            'verb': verb,
            'english': verb_info['english'],
            'tense': tense,
            'pronoun': pronoun,
            'correct_answer': verb_info['conjugations'][tense][pronoun]
        }

        return self.current_question

    def check_answer(self, user_answer: str) -> bool:
        """Check if user's answer is correct - very lenient!"""
        if not self.current_question:
            return False

        # Normalize both answers
        user_normalized = normalize_answer(user_answer)
        correct_normalized = normalize_answer(self.current_question['correct_answer'])

        # Accept if:
        # 1. Exact match: "habla"
        # 2. Contains the conjugation: "el habla", "ella habla", etc.
        correct = (
            user_normalized == correct_normalized or
            correct_normalized in user_normalized
        )

        self.questions_answered += 1
        if correct:
            self.score += 1

        return correct

    def is_complete(self) -> bool:
        """Check if session is complete"""
        return self.questions_answered >= self.total_questions


class ConjugationCog(BaseCog):
    """Simple, UX-focused conjugation practice"""

    def __init__(self, bot: commands.Bot):
        super().__init__(bot)
        self.active_games: Dict[int, GameSession] = {}
        self.verb_data = None
        self.categories = None
        self.default_category = "high-frequency"

    async def cog_load(self):
        """Load verb data"""
        logger.info("Loading verb data...")

        try:
            data_file = Path(__file__).parent / 'verb_data.json'
            with open(data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self.categories = data['categories']
            self.verb_data = data['verbs']

            total_verbs = len(self.verb_data)
            logger.info(f"✅ Loaded {total_verbs} verbs across {len(self.categories)} categories")

        except Exception as e:
            logger.error(f"❌ Failed to load verb data: {e}")
            raise

    @commands.command(name='conj', aliases=['conjugate'])
    async def start_game(self, ctx, category: str = None, questions: int = 10):
        """
        Start a conjugation practice session

        Usage:
          !conj                    → High frequency verbs, 10 questions
          !conj 15                 → High frequency verbs, 15 questions
          !conj regular-ar         → Regular -AR verbs, 10 questions
          !conj irregulars 20      → Irregular verbs, 20 questions

        Categories: high-frequency, regular-ar, regular-er-ir, irregulars
        """
        user_id = ctx.author.id

        # Check if already playing
        if user_id in self.active_games:
            game = self.active_games[user_id]
            embed = discord.Embed(
                title="⚠️ Game Already Active",
                description=f"You're currently playing **{game.category_name}**!\n\n"
                           f"Progress: {game.questions_answered}/{game.total_questions} • Score: {game.score}/{game.questions_answered if game.questions_answered > 0 else 0}",
                color=0xFEE75C
            )
            embed.set_footer(text="Type your answer or 'quit' to stop")
            await ctx.send(embed=embed)
            return

        # Parse arguments (handle if they passed number as first arg)
        if category and category.isdigit():
            questions = int(category)
            category = self.default_category
        elif not category:
            category = self.default_category

        # Validate category
        if category not in self.categories:
            valid_cats = ", ".join(self.categories.keys())
            embed = discord.Embed(
                title="❌ Invalid Category",
                description=f"Category `{category}` not found.\n\n**Available categories:**\n{valid_cats}",
                color=0xED4245
            )
            await ctx.send(embed=embed)
            return

        # Validate question count
        questions = max(1, min(questions, 30))

        # Create game session
        category_data = self.categories[category]
        game = GameSession(
            user_id=user_id,
            channel_id=ctx.channel.id,
            category=category,
            category_data=category_data,
            verb_data={v: self.verb_data[v] for v in category_data['verbs'] if v in self.verb_data},
            total_questions=questions
        )
        self.active_games[user_id] = game

        # Send welcome message
        embed = discord.Embed(
            title="🎮 ¡Vamos! Let's Practice",
            description=f"**{category_data['name']}**\n{category_data['description']}",
            color=0x57F287
        )
        embed.add_field(
            name="Session Info",
            value=f"📝 {questions} questions\n🎯 {len(game.available_tenses)} tenses\n📚 {len(game.available_verbs)} verbs",
            inline=False
        )
        embed.set_footer(text="Just type the conjugation (with or without pronoun) • 'quit' to stop")
        await ctx.send(embed=embed)

        # Generate and send first question
        game.generate_question()
        question_embed = self._create_question_embed(game)
        await ctx.send(embed=question_embed)

        logger.info(f"Started conjugation game for user {user_id}: {category}, {questions}q")

    @commands.command(name='conj_categories', aliases=['conj_cats'])
    async def show_categories(self, ctx):
        """Show all available practice categories"""
        embed = discord.Embed(
            title="📚 Practice Categories",
            description="Choose your focus area for conjugation practice",
            color=0x5865F2
        )

        for cat_id, cat_data in self.categories.items():
            verb_count = len(cat_data['verbs'])
            tense_count = len(cat_data['tenses'])
            embed.add_field(
                name=f"{cat_data['name']}",
                value=f"*{cat_data['description']}*\n`{verb_count} verbs • {tense_count} tenses`\n\nUse: `!conj {cat_id}`",
                inline=False
            )

        embed.set_footer(text="!conj [category] [questions] to start practicing")
        await ctx.send(embed=embed)

    @commands.command(name='conj_stop')
    async def stop_game(self, ctx):
        """Stop your current practice session"""
        user_id = ctx.author.id

        if user_id not in self.active_games:
            embed = discord.Embed(
                title="❌ No Active Game",
                description="You don't have an active practice session.",
                color=0xED4245
            )
            await ctx.send(embed=embed)
            return

        game = self.active_games[user_id]
        del self.active_games[user_id]

        # Show final results
        embed = self._create_results_embed(game, stopped=True)
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message):
        """Listen for answers to conjugation questions"""
        # Ignore bots
        if message.author.bot:
            return

        # Ignore commands
        prefix = getattr(self.bot, 'command_prefix', '!')
        if isinstance(prefix, str) and message.content.startswith(prefix):
            return

        user_id = message.author.id

        # Check if user has active game
        if user_id not in self.active_games:
            return

        game = self.active_games[user_id]

        # Only respond in game channel
        if message.channel.id != game.channel_id:
            return

        user_answer = message.content.strip()

        # Handle quit
        if user_answer.lower() in ['quit', 'stop', 'exit']:
            del self.active_games[user_id]
            embed = self._create_results_embed(game, stopped=True)
            await message.channel.send(embed=embed)
            return

        # Check answer
        correct = game.check_answer(user_answer)

        # Send feedback
        feedback_embed = self._create_feedback_embed(game, user_answer, correct)
        await message.channel.send(embed=feedback_embed)

        # Check if game is complete
        if game.is_complete():
            del self.active_games[user_id]
            results_embed = self._create_results_embed(game, stopped=False)
            await message.channel.send(embed=results_embed)
            return

        # Generate next question
        import asyncio
        await asyncio.sleep(1.5)  # Brief pause before next question
        game.generate_question()
        question_embed = self._create_question_embed(game)
        await message.channel.send(embed=question_embed)

    def _create_question_embed(self, game: GameSession) -> discord.Embed:
        """Create question embed"""
        q = game.current_question
        progress = f"{game.questions_answered + 1}/{game.total_questions}"

        # Tense display names
        tense_names = {
            "presente": "Present",
            "pretérito": "Preterite (Simple Past)",
            "futuro": "Future"
        }
        tense_display = tense_names.get(q['tense'], q['tense'])

        # Simplify pronoun for less confusion
        display_pronoun = simplify_pronoun(q['pronoun'])

        embed = discord.Embed(
            title=f"Question {progress}",
            description=f"# {display_pronoun} + {q['verb']}\n*{q['english']}*",
            color=0x5865F2
        )

        embed.add_field(
            name="Tense",
            value=tense_display,
            inline=True
        )

        if game.questions_answered > 0:
            accuracy = (game.score / game.questions_answered) * 100
            embed.add_field(
                name="Score",
                value=f"{game.score}/{game.questions_answered} ({accuracy:.0f}%)",
                inline=True
            )

        embed.set_footer(text=f"{game.category_name} • Just type the conjugation (e.g. 'habla') or 'quit'")

        return embed

    def _create_feedback_embed(self, game: GameSession, user_answer: str, correct: bool) -> discord.Embed:
        """Create feedback embed after answer"""
        q = game.current_question
        display_pronoun = simplify_pronoun(q['pronoun'])

        if correct:
            embed = discord.Embed(
                title="✅ ¡Correcto!",
                description=f"**{display_pronoun} {q['correct_answer']}**",
                color=0x57F287
            )
        else:
            embed = discord.Embed(
                title="❌ Not quite",
                description=f"You said: **{user_answer}**\nCorrect answer: **{display_pronoun} {q['correct_answer']}**",
                color=0xED4245
            )

        # Show current score
        accuracy = (game.score / game.questions_answered) * 100
        embed.add_field(
            name="Current Score",
            value=f"{game.score}/{game.questions_answered} ({accuracy:.0f}%)",
            inline=True
        )

        return embed

    def _create_results_embed(self, game: GameSession, stopped: bool) -> discord.Embed:
        """Create final results embed"""
        if stopped:
            title = "👋 Practice Stopped"
        else:
            title = "🎉 Practice Complete!"

        if game.questions_answered == 0:
            description = "No questions answered yet."
        else:
            accuracy = (game.score / game.questions_answered) * 100
            description = f"Final Score: **{game.score}/{game.questions_answered}** ({accuracy:.0f}%)"

            # Add encouraging message based on performance
            if accuracy == 100:
                description += "\n\n¡Perfecto! 🌟 Amazing work!"
            elif accuracy >= 80:
                description += "\n\n¡Excelente! 🎯 Great job!"
            elif accuracy >= 60:
                description += "\n\n¡Bien hecho! 👍 Good effort!"
            else:
                description += "\n\n¡Sigue practicando! 💪 Keep practicing!"

        color = 0x57F287 if not stopped else 0xFEE75C
        embed = discord.Embed(
            title=title,
            description=description,
            color=color
        )

        embed.add_field(
            name="Category",
            value=game.category_name,
            inline=True
        )

        prefix = getattr(self.bot, 'command_prefix', '!')
        embed.set_footer(text=f"Use {prefix}conj to practice again!")

        return embed


async def setup(bot):
    await bot.add_cog(ConjugationCog(bot))
