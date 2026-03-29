"""Gemini client for generating language learning conversations."""
import logging

from cogs.utils.gemini_base import BaseGeminiClient

from .conversation_data import CATEGORIES, LANGUAGES, LEVELS

logger = logging.getLogger(__name__)


class ConversationGeminiClient(BaseGeminiClient):
    """Generates structured language learning conversations via Gemini."""

    async def generate_conversation(
        self, language: str, level: str, category: str, scenario: str,
    ) -> dict | None:
        """Generate a conversation. Returns parsed dict or None."""
        level_data = LEVELS[level]
        prompt = self._create_conversation_prompt(language, level, category, scenario)

        text = await self._generate_with_retry(
            prompt, temperature=level_data['temperature'],
        )
        if not text:
            return None

        result = self._parse_response(text)
        if result:
            logger.info("Generated %s %s %s conversation", language, level, category)
        else:
            logger.warning("Failed to parse conversation response")
        return result

    def _create_conversation_prompt(
        self, language: str, level: str, category: str, scenario: str,
    ) -> str:
        level_data = LEVELS[level]
        lang_data = LANGUAGES[language]
        category_data = CATEGORIES[category]

        return f"""You are a language learning conversation generator. Generate a realistic, natural conversation in {lang_data['name']} for language learners at the {level_data['name']} level ({level_data['description']}).

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

    def _parse_response(self, text: str) -> dict | None:
        """Parse structured SCENARIO/SPEAKER/CONVERSATION response."""
        try:
            scenario = speaker1 = speaker2 = None
            conversation_lines = []
            in_conversation = False

            for line in text.strip().split('\n'):
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
                elif in_conversation and ':' in line:
                    conversation_lines.append(line)

            if not all([scenario, speaker1, speaker2, conversation_lines]):
                logger.warning(
                    "Missing fields — scenario=%s speaker1=%s speaker2=%s lines=%s",
                    bool(scenario), bool(speaker1), bool(speaker2), len(conversation_lines),
                )
                return None

            if len(conversation_lines) < 6:
                logger.warning("Short conversation: %s exchanges", len(conversation_lines))

            return {
                'scenario': scenario,
                'speaker1': speaker1,
                'speaker2': speaker2,
                'conversation': '\n'.join(conversation_lines),
            }
        except Exception:
            logger.exception("Error parsing conversation response")
            return None
