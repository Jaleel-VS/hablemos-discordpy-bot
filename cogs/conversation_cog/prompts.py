"""Prompts used by ``conversation_cog``.

One stateless prompt: :data:`CONVERSATION_PROMPT`. Given a language,
level, category, and scenario, it asks Gemini to produce a structured
two-speaker conversation in a strict ``SCENARIO:`` / ``SPEAKER1:`` /
``SPEAKER2:`` / ``CONVERSATION:`` format and parses the response into
a typed :class:`ParsedConversation` (or ``None`` if the response
doesn't satisfy the contract).

The parser is the biggest test-surface gain of the Gemini-deep-module
migration: previously it lived inside the per-cog client wrapper
without any tests; now it's a pure ``parse(text, inp)`` function.
"""
import logging
from dataclasses import dataclass

from cogs.utils.gemini import Prompt

from .conversation_data import CATEGORIES, LANGUAGES, LEVELS

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ConversationInput:
    """Input for :class:`ConversationPrompt`."""
    language: str  # key into LANGUAGES
    level: str     # key into LEVELS
    category: str  # key into CATEGORIES
    scenario: str  # specific situation prompt


@dataclass(frozen=True, slots=True)
class ParsedConversation:
    """Parsed Gemini response for a generated conversation."""
    scenario: str
    speaker1: str
    speaker2: str
    conversation: str  # joined CONVERSATION: lines


class ConversationPrompt(Prompt[ConversationInput, ParsedConversation | None]):
    """Generate a structured two-speaker language-learning conversation."""

    feature = "conversation"
    # Per-level temperature variation lives below in resolve_temperature;
    # this attribute is the safe fallback only.
    temperature = 0.7
    max_output_tokens = 2048

    def resolve_temperature(self, inp: ConversationInput) -> float:
        return LEVELS[inp.level]["temperature"]

    def render(self, inp: ConversationInput) -> str:
        level_data = LEVELS[inp.level]
        lang_data = LANGUAGES[inp.language]
        category_data = CATEGORIES[inp.category]

        return f"""You are a language learning conversation generator. Generate a realistic, natural conversation in {lang_data['name']} for language learners at the {level_data['name']} level ({level_data['description']}).

**Scenario Category:** {category_data['name']} {category_data['emoji']}
**Specific Situation:** {inp.scenario}
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

    def parse(self, text: str, inp: ConversationInput) -> ParsedConversation | None:
        if not text:
            return None
        try:
            scenario: str | None = None
            speaker1: str | None = None
            speaker2: str | None = None
            conversation_lines: list[str] = []
            in_conversation = False

            for raw in text.strip().split("\n"):
                line = raw.strip()
                if not line:
                    continue
                if line.startswith("SCENARIO:"):
                    scenario = line[len("SCENARIO:"):].strip()
                elif line.startswith("SPEAKER1:"):
                    speaker1 = line[len("SPEAKER1:"):].strip()
                elif line.startswith("SPEAKER2:"):
                    speaker2 = line[len("SPEAKER2:"):].strip()
                elif line.startswith("CONVERSATION:"):
                    in_conversation = True
                elif in_conversation and ":" in line:
                    conversation_lines.append(line)

            if not (scenario and speaker1 and speaker2 and conversation_lines):
                logger.warning(
                    "Conversation parse missing fields "
                    "(scenario=%s speaker1=%s speaker2=%s lines=%s) for %s/%s/%s",
                    bool(scenario), bool(speaker1), bool(speaker2),
                    len(conversation_lines),
                    inp.language, inp.level, inp.category,
                )
                return None

            if len(conversation_lines) < 6:
                logger.warning(
                    "Short conversation (%s exchanges) for %s/%s/%s",
                    len(conversation_lines), inp.language, inp.level, inp.category,
                )

            return ParsedConversation(
                scenario=scenario,
                speaker1=speaker1,
                speaker2=speaker2,
                conversation="\n".join(conversation_lines),
            )
        except Exception:
            logger.exception(
                "Error parsing conversation response for %s/%s/%s",
                inp.language, inp.level, inp.category,
            )
            return None


CONVERSATION_PROMPT = ConversationPrompt()


__all__ = [
    "CONVERSATION_PROMPT",
    "ConversationInput",
    "ConversationPrompt",
    "ParsedConversation",
]
