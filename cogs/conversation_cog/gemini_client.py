"""
Google Gemini API client for generating language learning conversations
"""
import os
import logging
import time
import random
import asyncio
from typing import List, Dict, Optional
from google import genai
from google.genai import types
from .conversation_data import LEVELS, LANGUAGES, CATEGORIES

logger = logging.getLogger(__name__)


class RateLimiter:
    """Rate limiter for Gemini API calls"""

    def __init__(self, requests_per_minute: int = 15):
        self.rpm = requests_per_minute
        self.requests = []

    async def wait_if_needed(self):
        """Wait if we're at rate limit"""
        now = time.time()

        # Remove requests older than 1 minute
        self.requests = [r for r in self.requests if now - r < 60]

        if len(self.requests) >= self.rpm:
            # Calculate wait time
            oldest = self.requests[0]
            wait_time = 60 - (now - oldest) + 0.5  # +0.5 for safety

            if wait_time > 0:
                logger.info(f"Rate limit reached, waiting {wait_time:.1f}s")
                await asyncio.sleep(wait_time)

        # Record this request
        self.requests.append(time.time())


class ConversationGeminiClient:
    """Wrapper for Google Gemini API for conversation generation"""

    def __init__(self):
        """
        Initialize Gemini client for conversations

        Raises:
            ValueError: If GEMINI_API_KEY environment variable is not set
        """
        # Get API key from environment
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is required")

        # Initialize the client with API key
        self.client = genai.Client(api_key=api_key)

        # Model to use - gemini-2.0-flash-lite is free tier compatible
        self.model_name = 'gemini-2.0-flash-lite'

        # Rate limiter for API calls
        self.rate_limiter = RateLimiter(requests_per_minute=15)

        logger.info("Conversation Gemini client initialized successfully")

    async def generate_conversation(self, language: str, level: str,
                                   category: str, scenario: str,
                                   max_retries: int = 3) -> Optional[Dict]:
        """
        Generate a conversation with retry logic

        Args:
            language: Target language (spanish/english)
            level: Difficulty level (beginner/intermediate/advanced)
            category: Conversation category (restaurant/travel/etc)
            scenario: Specific scenario description
            max_retries: Maximum retry attempts

        Returns:
            Dict with keys: scenario, speaker1, speaker2, conversation
            or None if generation fails
        """
        for attempt in range(max_retries):
            try:
                # Wait if needed for rate limiting
                await self.rate_limiter.wait_if_needed()

                # Create the prompt
                prompt = self._create_conversation_prompt(
                    language, level, category, scenario
                )

                # Set temperature based on level
                level_data = LEVELS[level]
                temperature = level_data['temperature']

                # Generate conversation
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=temperature,
                        top_p=0.9,
                        top_k=40,
                        max_output_tokens=2048,
                    )
                )

                # Parse response
                conversation_data = self._parse_conversation_response(response.text)

                if conversation_data:
                    logger.info(f"Successfully generated {language} {level} {category} conversation")
                    return conversation_data
                else:
                    logger.warning(f"Failed to parse conversation (attempt {attempt+1})")

            except Exception as e:
                logger.error(f"Gemini API error (attempt {attempt+1}): {e}")

                # Exponential backoff
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    await asyncio.sleep(wait_time)

        return None

    def _create_conversation_prompt(self, language: str, level: str,
                                   category: str, scenario: str) -> str:
        """
        Create prompt for generating a conversation

        Returns a structured prompt that guides Gemini to create
        an appropriate language learning conversation.
        """
        level_data = LEVELS[level]
        lang_data = LANGUAGES[language]
        category_data = CATEGORIES[category]

        prompt = f"""You are a language learning conversation generator. Generate a realistic, natural conversation in {lang_data['name']} for language learners at the {level_data['name']} level ({level_data['description']}).

**Scenario Category:** {category_data['name']} {category_data['emoji']}
**Specific Situation:** {scenario}
**Language:** {lang_data['name']}
**Level:** {level_data['name']} ({level_data['description']})

**CRITICAL REQUIREMENTS:**
1. The ENTIRE conversation must be in {lang_data['name']} ONLY - no translations or explanations in other languages
2. Create exactly 2 speakers with realistic names appropriate for {lang_data['name']}-speaking culture
3. Generate {level_data['exchange_count'][0]}-{level_data['exchange_count'][1]} total exchanges (alternating between speakers)
4. Each speaker should have 3-4 turns total
5. Make the conversation natural and realistic - avoid being overly educational or artificial
6. Include cultural context appropriate to {lang_data['name']}-speaking regions

**Language Level Guidelines for {level_data['name']}:**
- Vocabulary: {level_data['vocabulary_guidance']}
- Grammar: {level_data['grammar_guidance']}

**Output Format:**
You must output EXACTLY in this format (no additional text before or after):

SCENARIO: [One sentence describing the situation in {lang_data['name']}]
SPEAKER1: [Name and role, e.g., "María (camarera)" or "John (customer)"]
SPEAKER2: [Name and role, e.g., "Carlos (cliente)" or "Sarah (server)"]
CONVERSATION:
[Speaker1 Name]: [First message]
[Speaker2 Name]: [Response]
[Speaker1 Name]: [Next message]
[Continue alternating for {level_data['exchange_count'][0]}-{level_data['exchange_count'][1]} total exchanges]

**Example Structure for SPANISH (DO NOT COPY - create original content):**
SCENARIO: Estás ordenando comida en un restaurante familiar
SPEAKER1: Ana (mesera)
SPEAKER2: Miguel (cliente)
CONVERSATION:
Ana: Buenas tardes. ¿Está listo para ordenar?
Miguel: Sí, por favor. ¿Qué me recomienda?
Ana: El pollo asado es muy popular hoy.
Miguel: Perfecto, tomaré eso.
Ana: ¿Y para tomar?
Miguel: Una limonada, gracias.
Ana: Enseguida se lo traigo.
Miguel: Muchas gracias.

**Example Structure for ENGLISH (DO NOT COPY - create original content):**
SCENARIO: You are checking into a hotel
SPEAKER1: Tom (hotel receptionist)
SPEAKER2: Lisa (guest)
CONVERSATION:
Tom: Good evening! Welcome to our hotel.
Lisa: Thank you! I have a reservation.
Tom: May I have your name, please?
Lisa: It's Lisa Johnson.
Tom: Here we are. Room 305.
Lisa: Is breakfast included?
Tom: Yes, from 7 to 10 AM.
Lisa: Perfect, thank you!

**IMPORTANT REMINDERS:**
- NO English translations if generating Spanish
- NO Spanish translations if generating English
- NO vocabulary notes
- NO grammar explanations
- ONLY the formatted conversation as shown above
- Make it feel like a real conversation between real people
- Ensure appropriate complexity for {level_data['name']} level
- Use culturally appropriate names and contexts

Generate the conversation now:"""

        return prompt

    def _parse_conversation_response(self, response_text: str) -> Optional[Dict]:
        """
        Parse the structured response from Gemini

        Expected format:
        SCENARIO: [text]
        SPEAKER1: [name]
        SPEAKER2: [name]
        CONVERSATION:
        [Speaker]: [message]
        ...

        Returns:
            Dict with scenario, speaker1, speaker2, conversation keys
            or None if parsing fails
        """
        try:
            lines = response_text.strip().split('\n')

            scenario = None
            speaker1 = None
            speaker2 = None
            conversation_lines = []
            in_conversation = False

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                if line.startswith('SCENARIO:'):
                    scenario = line.replace('SCENARIO:', '').strip()
                elif line.startswith('SPEAKER1:'):
                    speaker1 = line.replace('SPEAKER1:', '').strip()
                elif line.startswith('SPEAKER2:'):
                    speaker2 = line.replace('SPEAKER2:', '').strip()
                elif line.startswith('CONVERSATION:'):
                    in_conversation = True
                elif in_conversation:
                    # This is a conversation line
                    if ':' in line:
                        conversation_lines.append(line)

            # Validate we got everything
            if not all([scenario, speaker1, speaker2, conversation_lines]):
                logger.error(f"Missing required fields. Scenario: {scenario}, Speaker1: {speaker1}, Speaker2: {speaker2}, Lines: {len(conversation_lines)}")
                logger.debug(f"Raw response: {response_text[:500]}")
                return None

            # Validate we have enough exchanges
            if len(conversation_lines) < 6:
                logger.warning(f"Conversation too short: only {len(conversation_lines)} exchanges")
                # Still return it, might be acceptable

            # Join conversation lines
            conversation_text = '\n'.join(conversation_lines)

            return {
                'scenario': scenario,
                'speaker1': speaker1,
                'speaker2': speaker2,
                'conversation': conversation_text
            }

        except Exception as e:
            logger.error(f"Error parsing conversation response: {e}")
            logger.debug(f"Response text: {response_text[:500]}")
            return None
