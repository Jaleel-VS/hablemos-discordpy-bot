"""
Google Gemini API client for generating conversation summaries.
"""
import os
import logging

from google import genai
from google.genai import types

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


class GeminiClient:
    """Wrapper for Google Gemini API for conversation summarization."""

    def __init__(self):
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is required")

        self.client = genai.Client(api_key=api_key)
        self.model_name = 'gemini-2.0-flash-lite'
        logger.info("Gemini client initialized successfully")

    def generate_summary(self, messages: list[dict]) -> str:
        """
        Generate conversation summary from messages.

        Args:
            messages: list of dicts with 'author', 'content', 'timestamp'

        Returns:
            Summary text.
        """
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

        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
                max_output_tokens=1024,
            ),
        )

        logger.info(f"Generated summary for {len(messages)} messages")
        return response.text
