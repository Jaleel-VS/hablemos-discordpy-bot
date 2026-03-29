"""Gemini client for generating conversation summaries."""
import logging

from cogs.utils.gemini_base import BaseGeminiClient

logger = logging.getLogger(__name__)

SUMMARY_PROMPT = """Summarize this Discord conversation for a moderator. Be concise and factual.

Rules:
- Use markdown bullet points
- Name participants when relevant
- Skip greetings, small talk, and bot commands unless they're the main topic
- If there are multiple threads/topics, separate them
- Max 400 words
- Do not editorialize or add opinions

{message_count} messages between {start_time} and {end_time}:

{messages}"""


class GeminiClient(BaseGeminiClient):
    """Generates conversation summaries via Gemini."""

    async def generate_summary(self, messages: list[dict]) -> str:
        """Generate a summary from a list of message dicts."""
        if not messages:
            return "No messages to summarize."

        formatted = []
        for msg in messages:
            content = msg['content'].strip()
            if not content:
                continue
            ts = msg['timestamp'].strftime('%H:%M')
            formatted.append(f"[{ts}] {msg['author']}: {content}")

        prompt = SUMMARY_PROMPT.format(
            message_count=len(messages),
            start_time=messages[0]['timestamp'].strftime('%Y-%m-%d %H:%M'),
            end_time=messages[-1]['timestamp'].strftime('%Y-%m-%d %H:%M'),
            messages='\n'.join(formatted),
        )

        text = await self._generate(prompt, temperature=0.2, max_output_tokens=1024)
        logger.info("Generated summary for %s messages", len(messages))
        return text or "Failed to generate summary."
