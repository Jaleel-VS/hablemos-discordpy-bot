import asyncio
import logging
import random
from typing import Dict
import discord
from discord.ext import commands
from .conjugation_game import ConjugationGame
from base_cog import BaseCog

# Set up logger for this module
logger = logging.getLogger(__name__)

class ConjugationController(BaseCog):
    def __init__(self, bot):
        super().__init__(bot)
        self.active_games: Dict[int, ConjugationGame] = {}  # user_id -> game instance
        self._game_locks: Dict[int, asyncio.Lock] = {}  # user_id -> lock
        self.verb_data = None  # Will be loaded in cog_load
        self.loading_failed = False
        self._timeout_task = None  # Background task for timeout monitoring

    async def cog_load(self):
        """Load verb data when the cog initializes"""
        logger.info("Loading Spanish verb conjugation data...")
        
        try:
            from .xml_parser import SpanishVerbParser
            import os
            
            # Get XML file paths
            cog_dir = os.path.dirname(__file__)
            verbs_xml = os.path.join(cog_dir, 'data', 'verbs-es.xml')
            conjugations_xml = os.path.join(cog_dir, 'data', 'conjugations-es.xml')
            
            # Parse XML data
            parser = SpanishVerbParser(verbs_xml, conjugations_xml)
            parser.parse_conjugation_templates()
            parser.parse_verbs()
            self.verb_data = parser.get_common_verbs(200)
            
            logger.info(f"Successfully loaded {len(self.verb_data)} verbs with all conjugations")
            
            # Start timeout monitoring task
            self._timeout_task = asyncio.create_task(self._monitor_timeouts())
            logger.info("Started session timeout monitoring")
            
        except Exception as e:
            logger.error(f"Failed to load verb data: {e}")
            self.loading_failed = True
            # Set minimal fallback data
            self.verb_data = [
                {
                    "infinitive": "hablar",
                    "english": "to speak",
                    "conjugations": {
                        "indicativo": {
                            "presente": {
                                "yo": "hablo", "tú": "hablas", "él/ella": "habla",
                                "nosotros": "hablamos", "vosotros": "habláis", "ellos/ellas": "hablan"
                            }
                        }
                    },
                    "difficulty": "beginner",
                    "frequency_rank": 1
                }
            ]
            
            # Start timeout monitoring even with fallback data
            self._timeout_task = asyncio.create_task(self._monitor_timeouts())

    async def cog_unload(self):
        """Clean up when cog is unloaded"""
        if self._timeout_task:
            self._timeout_task.cancel()
            try:
                await self._timeout_task
            except asyncio.CancelledError:
                pass
        
        # Clean up active games
        self.active_games.clear()
        self._game_locks.clear()
        logger.info("Conjugation cog unloaded and cleaned up")

    async def _monitor_timeouts(self):
        """Background task to monitor and clean up timed out sessions"""
        while True:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds
                
                timed_out_users = []
                for user_id, game in self.active_games.items():
                    if game.is_timed_out():
                        timed_out_users.append(user_id)
                
                # Clean up timed out sessions
                for user_id in timed_out_users:
                    async with self._get_user_lock(user_id):
                        if user_id in self.active_games:
                            game = self.active_games[user_id]
                            del self.active_games[user_id]
                            
                            # Try to notify user about timeout
                            try:
                                user = self.bot.get_user(user_id)
                                if user:
                                    embed = discord.Embed(
                                        title="⏰ Session Timed Out",
                                        description=f"Your conjugation session ended due to 90 seconds of inactivity.\n\nFinal Score: **{game.score}/{game.questions_answered}**",
                                        color=0xf39c12
                                    )
                                    
                                    if game.questions_answered > 0:
                                        percentage = (game.score / game.questions_answered) * 100
                                        embed.add_field(
                                            name="Accuracy",
                                            value=f"{percentage:.1f}%",
                                            inline=True
                                        )
                                    
                                    prefix = self.bot.command_prefix if isinstance(self.bot.command_prefix, str) else '$'
                                    embed.set_footer(text=f"Use {prefix}conj to start a new session")
                                    
                                    # Send to user's DM or try to find a mutual channel
                                    try:
                                        await user.send(embed=embed)
                                    except discord.Forbidden:
                                        # Can't DM user, try to find a channel where the game was active
                                        if hasattr(game, 'channel_id'):
                                            channel = self.bot.get_channel(game.channel_id)
                                            if channel:
                                                await channel.send(f"{user.mention}, your conjugation session timed out!", embed=embed)
                                                
                            except Exception as e:
                                logger.warning(f"Failed to notify user {user_id} about timeout: {e}")
                                
                if timed_out_users:
                    logger.info(f"Cleaned up {len(timed_out_users)} timed out conjugation sessions")
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in timeout monitoring: {e}")

    def _get_user_lock(self, user_id: int) -> asyncio.Lock:
        """Get or create a lock for the specified user."""
        if user_id not in self._game_locks:
            self._game_locks[user_id] = asyncio.Lock()
        return self._game_locks[user_id]
    
    def get_random_verb(self):
        """Get a random verb from the loaded data"""
        if not self.verb_data:
            return None
        return random.choice(self.verb_data)
    
    def get_verbs_by_difficulty(self, difficulty: str):
        """Get verbs filtered by difficulty"""
        if not self.verb_data:
            return []
        return [verb for verb in self.verb_data if verb.get('difficulty') == difficulty]

    @commands.command(name='conjugate', aliases=['conj'])
    async def start_conjugation(self, ctx, questions: int = 10, mood: str = 'indicativo', 
                               difficulty: str = None, *tenses):
        """
        Start a conjugation practice session
        
        Parameters:
        - questions: Number of questions (1-20, default: 10)
        - mood: indicativo, subjuntivo (default: indicativo)  
        - difficulty: beginner, intermediate, advanced (default: all)
        - tenses: specific tenses to practice (default: all for mood)
        
        Examples:
        $conj 15 indicativo beginner presente
        $conj 5 subjuntivo
        $conj 20 indicativo intermediate presente futuro
        """
        user_id = ctx.author.id
        
        # Validate parameters
        questions = max(1, min(questions, 20))  # Clamp between 1-20
        mood = mood.lower()
        if mood not in ['indicativo', 'subjuntivo', 'condicional', 'imperativo']:
            await ctx.send("❌ Mood must be 'indicativo', 'subjuntivo', 'condicional', or 'imperativo'")
            return
            
        if difficulty and difficulty.lower() not in ['beginner', 'intermediate', 'advanced']:
            await ctx.send("❌ Difficulty must be 'beginner', 'intermediate', or 'advanced'")
            return
            
        # Convert tenses list to lowercase and validate
        tense_list = [t.lower() for t in tenses] if tenses else None
        valid_tenses = {
            'indicativo': ['presente', 'pretérito-imperfecto', 'pretérito-perfecto-simple', 'futuro'],
            'subjuntivo': ['presente', 'pretérito-imperfecto-1', 'pretérito-imperfecto-2', 'futuro'],
            'condicional': ['presente'],
            'imperativo': ['afirmativo', 'negativo']
        }
        
        if tense_list:
            invalid_tenses = [t for t in tense_list if t not in valid_tenses[mood]]
            if invalid_tenses:
                await ctx.send(f"❌ Invalid tenses for {mood}: {', '.join(invalid_tenses)}\n"
                              f"Available: {', '.join(valid_tenses[mood])}")
                return
        
        async with self._get_user_lock(user_id):
            # Check if user already has an active game
            if user_id in self.active_games:
                embed = discord.Embed(
                    title="⚠️ Game Already Active",
                    description="You already have a conjugation game running! Type your answer or 'quit' to stop.",
                    color=0xFEE75C
                )
                await ctx.send(embed=embed)
                return

            # Check if data is loaded
            if not self.verb_data:
                await ctx.send("❌ Verb data not loaded. Please try again later.")
                return
                
            if self.loading_failed:
                await ctx.send("⚠️ Warning: Using limited fallback data due to loading issues.")

            # Create new game with parameters
            game = ConjugationGame(
                user_id=user_id, 
                channel_id=ctx.channel.id,
                session_length=questions,
                mood=mood,
                tenses=tense_list,
                difficulty=difficulty.lower() if difficulty else None,
                verb_data_source=self  # Pass the controller as data source
            )
            self.active_games[user_id] = game
            
            # Generate first question
            if not game.generate_question():
                await ctx.send("❌ No verbs available for the specified criteria. Try different settings.")
                return
            
            # Create start embed with session info
            embed = discord.Embed(
                title="🎮 Conjugation Practice Started!",
                description=f"**{questions} questions** • **{mood.title()}** mood",
                color=0x57F287
            )
            
            if tense_list:
                embed.add_field(
                    name="Tenses",
                    value=", ".join([t.replace('-', ' ').title() for t in tense_list]),
                    inline=True
                )
            
            if difficulty:
                embed.add_field(
                    name="Difficulty",
                    value=difficulty.title(),
                    inline=True
                )
            
            embed.set_footer(text="Type your answers or 'quit' to stop")
            await ctx.send(embed=embed)
            
            # Send first question
            question_embed = game.get_question_embed()
            if question_embed:
                await ctx.send(embed=question_embed)

    @commands.command(name='conjugate_stop', aliases=['conj_stop'])
    async def stop_conjugation(self, ctx):
        """Stop the current conjugation game"""
        user_id = ctx.author.id
        
        async with self._get_user_lock(user_id):
            if user_id not in self.active_games:
                embed = discord.Embed(
                    title="❌ No Active Game",
                    description="You don't have an active conjugation game.",
                    color=0xED4245
                )
                await ctx.send(embed=embed)
                return
            
            game = self.active_games[user_id]
            del self.active_games[user_id]
            
            # Show final score
            embed = discord.Embed(
                title="🏁 Game Finished!",
                description=f"Final Score: **{game.score}/{game.questions_answered}**",
                color=0x57F287
            )
            
            if game.questions_answered > 0:
                percentage = (game.score / game.questions_answered) * 100
                embed.add_field(
                    name="Accuracy",
                    value=f"{percentage:.1f}%",
                    inline=True
                )
            # Use the bot's configured prefix for footer hint
            prefix = self.bot.command_prefix if isinstance(self.bot.command_prefix, str) else '!'
            embed.set_footer(text=f"Great job practicing! Use {prefix}conjugate to start again.")
            await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message):
        """Listen for answers to conjugation questions"""
        # Ignore bot messages and messages that look like commands
        if message.author.bot:
            return
        # Honor the bot's configured prefix if available
        prefixes = []
        try:
            # commands.Bot.get_prefix can be coro depending on config; use command_prefix directly
            cp = getattr(self.bot, 'command_prefix', None)
            if isinstance(cp, str):
                prefixes = [cp]
            elif isinstance(cp, (list, tuple)):
                prefixes = list(cp)
        except Exception:
            prefixes = ['!', '$']
        if any(message.content.startswith(p) for p in prefixes):
            return
            
        user_id = message.author.id
        
        # Check if user has an active game
        if user_id not in self.active_games:
            return
            
        game = self.active_games[user_id]
        
        # Check for timeout before processing answer
        if game.is_timed_out():
            async with self._get_user_lock(user_id):
                if user_id in self.active_games:
                    del self.active_games[user_id]
            
            embed = discord.Embed(
                title="⏰ Session Timed Out",
                description=f"Your session ended due to inactivity.\nFinal Score: **{game.score}/{game.questions_answered}**",
                color=0xf39c12
            )
            await message.channel.send(embed=embed)
            return
        # Only process answers from the channel where the game started
        if getattr(game, 'channel_id', None) and message.channel.id != game.channel_id:
            return
        user_answer = message.content.strip()
        
        # Handle quit command
        if user_answer.lower() in ['quit', 'stop', 'exit']:
            async with self._get_user_lock(user_id):
                del self.active_games[user_id]
                
            embed = discord.Embed(
                title="👋 Game Stopped",
                description=f"Final Score: **{game.score}/{game.questions_answered}**",
                color=0x57F287
            )
            await message.channel.send(embed=embed)
            return
        
        # Check answer
        correct = game.check_answer(user_answer)
        
        # Send result
        result_embed = game.get_result_embed(correct, user_answer)
        if result_embed:
            await message.channel.send(embed=result_embed)
        
        # Check if session is complete
        if game.session_complete or game.questions_answered >= game.session_length:
            async with self._get_user_lock(user_id):
                del self.active_games[user_id]
                
            # Send final score
            embed = discord.Embed(
                title="🏁 Session Complete!",
                description=f"Final Score: **{game.score}/{game.questions_answered}**",
                color=0x57F287
            )
            
            if game.questions_answered > 0:
                percentage = (game.score / game.questions_answered) * 100
                embed.add_field(
                    name="Accuracy",
                    value=f"{percentage:.1f}%",
                    inline=True
                )
            
            prefix = self.bot.command_prefix if isinstance(self.bot.command_prefix, str) else '$'
            embed.set_footer(text=f"Great job! Use {prefix}conj to practice again.")
            await message.channel.send(embed=embed)
            return
        
        # Generate next question after a short delay
        await asyncio.sleep(1.5)
        next_question = game.generate_question()
        if next_question:
            question_embed = game.get_question_embed()
            if question_embed:
                await message.channel.send(embed=question_embed)
        else:
            # Session ended due to inability to generate questions
            async with self._get_user_lock(user_id):
                del self.active_games[user_id]
            await message.channel.send("Session ended - no more suitable questions available.")

    @commands.command(name='conjugate_help', aliases=['conj_help'])
    async def conjugation_help(self, ctx):
        """Show help for conjugation commands"""
        prefix = self.bot.command_prefix if isinstance(self.bot.command_prefix, str) else '!'
        embed = discord.Embed(
            title="🇪🇸 Conjugation Practice Help",
            description="Practice Spanish verb conjugations!",
            color=0x57F287
        )
        
        embed.add_field(
            name="Commands",
            value=f"""
            `{prefix}conj [questions] [mood] [difficulty] [tenses...]` - Start session
            `{prefix}conj_stop` - Stop current session
            `{prefix}conj_help` - Show this help
            """,
            inline=False
        )
        
        embed.add_field(
            name="Parameters",
            value=f"""
            **questions**: 1-20 (default: 10)
            **mood**: indicativo, subjuntivo (default: indicativo)
            **difficulty**: beginner, intermediate, advanced (default: all)
            **tenses**: presente, futuro, etc. (default: all for mood)
            """,
            inline=False
        )
        
        embed.add_field(
            name="How to Play",
            value="""
            1. Start a session with `!conjugate`
            2. You'll see a verb and pronoun to conjugate
            3. Type your answer in the chat
            4. Type 'quit' to stop anytime
            5. Session auto-ends after 90 seconds of inactivity
            """,
            inline=False
        )
        
        embed.add_field(
            name="Examples",
            value=f"""
            `{prefix}conj` - 10 questions, all indicativo tenses
            `{prefix}conj 5 subjuntivo` - 5 questions, subjunctive mood
            `{prefix}conj 15 indicativo beginner` - 15 questions, easy verbs only
            `{prefix}conj 10 indicativo intermediate presente futuro` - Present & future only
            """,
            inline=False
        )
        
        embed.set_footer(text="200 verbs • 5 tenses • 3 difficulty levels")
        await ctx.send(embed=embed)

    @commands.command(name='conjugate_options', aliases=['conj_options'])
    async def conjugation_options(self, ctx):
        """Show all available options for conjugation practice"""
        embed = discord.Embed(
            title="🎯 Conjugation Practice Options",
            description="Available settings for your practice sessions",
            color=0x3498db
        )
        
        embed.add_field(
            name="📊 Moods Available",
            value="• **Indicativo** (4 tenses)\n• **Subjuntivo** (4 tenses)\n• **Condicional** (1 tense)\n• **Imperativo** (2 forms)",
            inline=False
        )
        
        embed.add_field(
            name="⏰ Indicativo Tenses",
            value="• `presente` - I speak\n• `pretérito-imperfecto` - I was speaking\n• `pretérito-perfecto-simple` - I spoke\n• `futuro` - I will speak",
            inline=True
        )
        
        embed.add_field(
            name="🎭 Subjuntivo Tenses", 
            value="• `presente` - that I speak\n• `pretérito-imperfecto-1` - that I spoke (-ra)\n• `pretérito-imperfecto-2` - that I spoke (-se)\n• `futuro` - that I will speak",
            inline=True
        )
        
        embed.add_field(
            name="🤔 Other Moods",
            value="• **Condicional**: `presente` - I would speak\n• **Imperativo**: `afirmativo` - Speak!, `negativo` - Don't speak!",
            inline=False
        )
        
        embed.add_field(
            name="📈 Difficulty Levels",
            value="• **Beginner** (54 verbs) - Most common, regular patterns\n• **Intermediate** (91 verbs) - Common irregulars\n• **Advanced** (54 verbs) - Complex patterns, less frequent",
            inline=False
        )
        
        embed.add_field(
            name="📝 Session Lengths",
            value="• Minimum: 1 question\n• Maximum: 20 questions\n• Default: 10 questions", 
            inline=False
        )
        
        prefix = self.bot.command_prefix if isinstance(self.bot.command_prefix, str) else '$'
        embed.set_footer(text=f"Use {prefix}conj_help for examples and usage")
        await ctx.send(embed=embed)

    @commands.command(name='conjugate_status', aliases=['conj_status'])
    async def conjugation_status(self, ctx):
        """Show conjugation system status"""
        embed = discord.Embed(
            title="📊 Conjugation System Status",
            color=0x2ecc71 if self.verb_data and not self.loading_failed else 0xe74c3c
        )
        
        if not self.verb_data:
            embed.add_field(
                name="❌ Status",
                value="Verb data not loaded",
                inline=False
            )
        elif self.loading_failed:
            embed.add_field(
                name="⚠️ Status", 
                value="Using fallback data (limited functionality)",
                inline=False
            )
        else:
            embed.add_field(
                name="✅ Status",
                value="Fully operational",
                inline=False
            )
            
            embed.add_field(
                name="📚 Data Loaded",
                value=f"• {len(self.verb_data)} verbs\n• 4 moods\n• 11 tenses",
                inline=True
            )
            
            # Count difficulties
            diff_counts = {}
            for verb in self.verb_data:
                diff = verb.get('difficulty', 'unknown')
                diff_counts[diff] = diff_counts.get(diff, 0) + 1
                
            embed.add_field(
                name="📈 Difficulties",
                value="\n".join([f"• {d.title()}: {c}" for d, c in diff_counts.items()]),
                inline=True
            )
            
        embed.add_field(
            name="🎮 Active Games",
            value=f"{len(self.active_games)} games running",
            inline=True
        )
        
        # Show timeout monitoring status
        monitoring_status = "✅ Running" if self._timeout_task and not self._timeout_task.done() else "❌ Stopped"
        embed.add_field(
            name="⏰ Timeout Monitor",
            value=f"{monitoring_status} (90s timeout)",
            inline=True
        )
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(ConjugationController(bot))
