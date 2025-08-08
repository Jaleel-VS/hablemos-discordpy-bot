"""
Simple conjugation game class for MVP
"""
import random
import unicodedata
import asyncio
import time
import discord
from .conjugation_data import get_random_verb

def _normalize(text: str) -> str:
    if text is None:
        return ""
    text = text.strip().lower()
    # remove accents
    return ''.join(
        c for c in unicodedata.normalize('NFD', text)
        if unicodedata.category(c) != 'Mn'
    )

class ConjugationGame:
    def __init__(self, user_id, channel_id: int, session_length: int = 10, 
                 mood: str = 'indicativo', tenses: list = None, difficulty: str = None,
                 verb_data_source=None):
        self.user_id = user_id
        self.channel_id = channel_id
        self.session_length = min(max(session_length, 1), 20)  # 1-20 questions
        self.mood = mood.lower()
        self.tenses = tenses or self._get_default_tenses(mood)
        self.difficulty = difficulty
        self.verb_data_source = verb_data_source  # Controller or fallback to conjugation_data
        self.current_question = None
        self.score = 0
        self.questions_answered = 0
        self.active = True
        self.session_complete = False
        self.last_activity = time.time()  # Track last user activity
        self.timeout_seconds = 90  # 90 second timeout
        self.timed_out = False
        
    def _get_default_tenses(self, mood: str) -> list:
        """Get default tenses for a given mood"""
        defaults = {
            'indicativo': ['presente', 'pretérito-imperfecto', 'pretérito-perfecto-simple', 'futuro'],
            'subjuntivo': ['presente', 'pretérito-imperfecto-1', 'pretérito-imperfecto-2', 'futuro'],
            'condicional': ['presente'],
            'imperativo': ['afirmativo', 'negativo']
        }
        return defaults.get(mood, ['presente'])
        
    def generate_question(self):
        """Generate a new conjugation question"""
        # Check if session is complete
        if self.questions_answered >= self.session_length:
            self.session_complete = True
            return None
            
        # Get a verb that matches difficulty filter
        attempts = 0
        while attempts < 50:  # Prevent infinite loop
            # Use controller's data source if available, otherwise fallback
            if self.verb_data_source:
                verb_data = self.verb_data_source.get_random_verb()
            else:
                verb_data = get_random_verb()
            
            # Filter by difficulty if specified
            if self.difficulty and verb_data.get("difficulty", "beginner") != self.difficulty:
                attempts += 1
                continue
                
            # Check if verb has the required mood and tenses
            verb_conjugations = verb_data.get("conjugations", {})
            if self.mood not in verb_conjugations:
                attempts += 1
                continue
                
            available_tenses = list(verb_conjugations[self.mood].keys())
            valid_tenses = [t for t in self.tenses if t in available_tenses]
            
            if not valid_tenses:
                attempts += 1
                continue
                
            # Generate question
            tense = random.choice(valid_tenses)
            pronouns = list(verb_conjugations[self.mood][tense].keys())
            pronoun = random.choice(pronouns)
            
            self.current_question = {
                "verb": verb_data["infinitive"],
                "english": verb_data.get("english", ""),
                "mood": self.mood,
                "tense": tense,
                "pronoun": pronoun,
                "correct_answer": verb_conjugations[self.mood][tense][pronoun],
                "difficulty": verb_data.get("difficulty", "beginner"),
                "frequency_rank": verb_data.get("frequency_rank", 999)
            }
            
            return self.current_question
            
        # If we can't find a suitable verb, fall back to any available
        self.current_question = None
        return None
    
    def check_answer(self, user_answer):
        """Check if the user's answer is correct"""
        if not self.current_question:
            return False
            
        # Update activity timestamp
        self.last_activity = time.time()
            
        # Accept answers accent-insensitively and case-insensitively
        correct = _normalize(user_answer) == _normalize(self.current_question["correct_answer"]) 
        
        self.questions_answered += 1
        if correct:
            self.score += 1
            
        return correct
    
    def is_timed_out(self):
        """Check if the session has timed out due to inactivity"""
        if self.timed_out:
            return True
            
        inactive_time = time.time() - self.last_activity
        if inactive_time >= self.timeout_seconds:
            self.timed_out = True
            return True
            
        return False
    
    def get_time_remaining(self):
        """Get remaining time before timeout in seconds"""
        if self.timed_out:
            return 0
            
        inactive_time = time.time() - self.last_activity
        remaining = max(0, self.timeout_seconds - inactive_time)
        return remaining
    
    def get_question_embed(self):
        """Create a Discord embed for the current question"""
        if not self.current_question:
            return None
            
        q = self.current_question
        
        # Create title with session progress
        progress = f"({self.questions_answered + 1}/{self.session_length})"
        title = f"🇪🇸 Conjugation Practice {progress}"
        
        embed = discord.Embed(
            title=title,
            description=f"Conjugate **{q['verb']}** ({q.get('english', '')})",
            color=0x57F287
        )
        
        embed.add_field(
            name="Question",
            value=f"**{q['pronoun']}** + **{q['verb']}**",
            inline=False
        )
        
        # Show mood and tense
        tense_display = q['tense'].replace('-', ' ').title()
        embed.add_field(
            name="Mood & Tense",
            value=f"{q['mood'].title()} - {tense_display}",
            inline=True
        )
        
        embed.add_field(
            name="Score",
            value=f"{self.score}/{self.questions_answered}",
            inline=True
        )
        
        # Show difficulty and rank if available
        if q.get('difficulty') or q.get('frequency_rank'):
            info_parts = []
            if q.get('difficulty'):
                info_parts.append(f"Difficulty: {q['difficulty']}")
            if q.get('frequency_rank') and q['frequency_rank'] <= 200:
                info_parts.append(f"Rank: #{q['frequency_rank']}")
            
            if info_parts:
                embed.add_field(
                    name="Info",
                    value=" | ".join(info_parts),
                    inline=True
                )
        
        # Show time remaining in footer
        time_remaining = self.get_time_remaining()
        minutes = int(time_remaining // 60)
        seconds = int(time_remaining % 60)
        
        if time_remaining > 60:
            timeout_text = f"Timeout in {minutes}m {seconds}s"
        else:
            timeout_text = f"Timeout in {seconds}s"
            
        embed.set_footer(text=f"Type your answer or 'quit' to stop • {timeout_text}")
        
        return embed
    
    def get_result_embed(self, correct, user_answer):
        """Create a Discord embed for the answer result"""
        q = self.current_question
        
        if not q:
            return None
            
        if correct:
            embed = discord.Embed(
                title="✅ Correct!",
                description=f"**{q['pronoun']} {q['correct_answer']}**",
                color=0x57F287
            )
        else:
            embed = discord.Embed(
                title="❌ Incorrect",
                description=f"You answered: **{user_answer}**\nCorrect answer: **{q['pronoun']} {q['correct_answer']}**",
                color=0xED4245
            )
        
        embed.add_field(
            name="Score",
            value=f"{self.score}/{self.questions_answered}",
            inline=True
        )
        
        return embed
